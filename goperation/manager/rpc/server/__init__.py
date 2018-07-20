# -*- coding:utf-8 -*-
import time
import eventlet

from sqlalchemy import and_
from sqlalchemy import func

from simpleutil.config import cfg
from simpleutil.log import log as logging
from simpleutil.utils import importutils
from simpleutil.utils import jsonutils
from simpleutil.utils.timeutils import realnow
from simpleutil.common.exceptions import InvalidArgument

from simpleservice.rpc.target import Target
from simpleservice.rpc.exceptions import AMQPDestinationNotFound
from simpleservice.ormdb.exceptions import DBDuplicateEntry
from simpleservice.ormdb.exceptions import DBError
from simpleservice.ormdb.api import model_query
from simpleservice.loopingcall import IntervalLoopinTask

from goperation import threadpool
from goperation.utils import safe_func_wrapper
from goperation.manager import common as manager_common
from goperation.manager.api import get_client
from goperation.manager.api import get_session
from goperation.manager.api import get_cache
from goperation.manager.api import get_global
from goperation.manager.models import AsyncRequest
from goperation.manager.models import AgentEndpoint
from goperation.manager.models import AgentEntity
from goperation.manager.models import Agent
from goperation.manager.utils import targetutils
from goperation.manager.utils import responeutils
from goperation.manager.utils import resultutils

from goperation.manager.rpc.exceptions import RpcServerCtxtException
from goperation.manager.rpc.server import utils

from goperation.manager.rpc.base import RpcManagerBase


LOG = logging.getLogger(__name__)

CONF = cfg.CONF


class NOTFOUND(object):
    def __repr__(self):
        return 'Not Found'


NOTFOUND = NOTFOUND()


def iter_value(d, key):
    keys = key.split('.')
    value = d
    for k in keys:
        if value is None:
            raise InvalidArgument('%s error, None find' % key)
        value = value.get(k, NOTFOUND)
        if value is NOTFOUND:
            return NOTFOUND
    return value


class ChiocesResult(resultutils.ServerRpcResult):

    def __init__(self, chioces):
        super(ChiocesResult, self).__init__(host=CONF.host, resultcode=manager_common.RESULT_SUCCESS,
                                            result='chioces agents success')
        self.agents = chioces

    def to_dict(self):
        result = super(ChiocesResult, self).to_dict()
        result.setdefault('agents', self.agents)
        return result


class ExpiredAgentStatusTask(IntervalLoopinTask):

    def __init__(self, manager):
        self.manager = manager
        conf = CONF[manager_common.SERVER]
        self.interval = conf.expire_time
        super(ExpiredAgentStatusTask, self).__init__(periodic_interval=self.interval,
                                                     initial_delay=0,
                                                     stop_on_exception=False)

    def __call__(self, *args, **kwargs):
        deadline = int(time.time()) - self.interval
        for agent_id in self.manager.agents_loads:
            if self.manager.agents_loads[agent_id].get('time', 0) < deadline:
                self.manager.agents_loads.pop(agent_id)


# class NotifySendTask(IntervalLoopinTask):
#     """emergency"""
#     def __init__(self, manager):
#         self.manager = manager
#         conf = CONF[manager_common.SERVER]
#         super(NotifySendTask, self).__init__(periodic_interval=60*3,
#                                              initial_delay=15,
#                                              stop_on_exception=False)
#         self.notifys = {}


class RpcServerManager(RpcManagerBase):
    AYNCRUNCTXT = {'type': 'object',
                   'required': ['executer', 'ekwargs'],
                   'properties': {
                       'executer': {'type': 'string', 'description': '执行器'},
                       'ekwargs': {'type': 'object', 'description': '执行器运行参数'},
                       'condition': {'type': 'string', 'description': '条件校验'},
                       'ckwargs': {'type': 'object', 'description': '条件校验参数'}}
                   }

    def __init__(self):
        super(RpcServerManager, self).__init__(target=targetutils.target_rpcserver(CONF.host, fanout=True))
        self.conf = CONF[manager_common.SERVER]
        self.agents_loads = {}
        self.executers = {}
        self.conditions = {}

    def pre_start(self, external_objects):
        super(RpcServerManager, self).pre_start(external_objects)
        for executer in self.conf.executers:
            LOG.debug('Loading executer %s', executer)
            cls = importutils.import_class('goperation.manager.rpc.server.executer.%s.Executer' % executer)
            self.executers[executer] = cls
        for condition in self.conf.conditions:
            LOG.debug('Loading condition %s', condition)
            cls = importutils.import_class('goperation.manager.rpc.server.condition.%s.Condition' % condition)
            self.conditions[condition] = cls

    def post_start(self):
        self.force_status(manager_common.ACTIVE)
        self.add_periodic_task(ExpiredAgentStatusTask(self))

    def post_stop(self):
        super(RpcServerManager, self).post_stop()

    def full(self):
        if not self.is_active:
            return True
        with self.work_lock.priority(0):
            if self.status != manager_common.ACTIVE:
                return True
            if threadpool.pool.free() < 5:
                return True
        return False

    def _compile(self, position, rctxt):
        LOG.debug('try compile %s ctxt function' % position)
        jsonutils.schema_validate(rctxt, self.AYNCRUNCTXT)

        executer = rctxt.pop('executer')
        ekwargs = rctxt.pop('ekwargs', None)
        condition = rctxt.pop('condition', None)
        ckwargs = rctxt.pop('ckwargs', None)

        executer_cls = self.executers[executer]
        condition_cls = self.conditions[condition] if condition else None

        return executer_cls(ekwargs, condition_cls(position, ckwargs) if condition else None)

    def rpc_asyncrequest(self, ctxt,
                         asyncrequest, rpc_target, rpc_method,
                         rpc_ctxt, rpc_args):
        """async respone check"""
        session = get_session()
        finishtime = ctxt.get('finishtime', None)
        asyncrequest = AsyncRequest(**asyncrequest)

        pre_run = ctxt.pop('pre_run', None)
        after_run = ctxt.pop('after_run', None)
        post_run = ctxt.pop('post_run', None)

        if finishtime and int(realnow()) >= finishtime:
            asyncrequest.resultcode = manager_common.RESULT_OVER_FINISHTIME
            asyncrequest.result = 'Async request over finish time'
            asyncrequest.status = manager_common.FINISH
            try:
                session.add(asyncrequest)
                session.flush()
            except DBDuplicateEntry:
                LOG.warning('Async request record DBDuplicateEntry')
            except DBError as e:
                LOG.error('Async request record DBError %s: %s' % (e.__class__.__name__, e.message))
            return

        if not self.is_active:
            asyncrequest.resultcode = manager_common.SCHEDULER_STATUS_ERROR
            asyncrequest.result = 'Rpc server not active now'
            asyncrequest.status = manager_common.FINISH
            session.add(asyncrequest)
            session.flush()
            return

        try:
            if pre_run:
                pre_run = self._compile('pre', pre_run)
            if after_run:
                after_run = self._compile('after', after_run)
            if post_run:
                post_run = self._compile('post', post_run)
        except (KeyError, jsonutils.ValidationError):
            asyncrequest.resultcode = manager_common.SCHEDULER_EXECUTER_ERROR
            asyncrequest.result = 'Rpc server can not find executer or ctxt error'
            asyncrequest.status = manager_common.FINISH
            session.add(asyncrequest)
            session.flush()
            return
        # except Exception:
        #     LOG.exception('wtf')
        #     raise

        if rpc_ctxt.get('agents') is None:
            wait_agents = [x[0] for x in model_query(session, Agent.agent_id,
                                                     filter=Agent.status > manager_common.DELETED).all()]
        else:
            wait_agents = rpc_ctxt.get('agents')
        rpc_ctxt.update({'request_id': asyncrequest.request_id,
                         'expire': asyncrequest.expire,
                         'finishtime': asyncrequest.finishtime})

        try:
            target = Target(**rpc_target)
            rpc = get_client()
        except Exception:
            LOG.error('Prepare rpc clinet error')
            asyncrequest.resultcode = manager_common.SCHEDULER_PREPARE_ERROR
            asyncrequest.result = 'Rpc server prepare rpc clinet error'
            asyncrequest.status = manager_common.FINISH
            session.add(asyncrequest)
            session.flush()
            return

        if pre_run:
            try:
                pre_run.run(asyncrequest, wait_agents)
            except RpcServerCtxtException as e:
                asyncrequest.resultcode = manager_common.SCHEDULER_EXECUTER_ERROR
                asyncrequest.result = 'Rpc server ctxt pre function fail: %s' % e.message
                asyncrequest.status = manager_common.FINISH
                session.add(asyncrequest)
                session.flush()
                return

        session.add(asyncrequest)
        session.flush()

        LOG.debug('Try cast rpc method %s' % rpc_method)

        try:
            rpc.cast(target, ctxt=rpc_ctxt, msg={'method': rpc_method, 'args': rpc_args})
        except AMQPDestinationNotFound:
            asyncrequest.resultcode = manager_common.SEND_FAIL
            asyncrequest.result = 'Async %s request send fail, AMQPDestinationNotFound' % rpc_method
            asyncrequest.status = manager_common.FINISH
            session.flush()
            return

        LOG.debug('Cast %s to %s success' % (asyncrequest.request_id, target.to_dict()))

        if after_run:
            try:
                after_run.run(asyncrequest, wait_agents)
            except RpcServerCtxtException as e:
                asyncrequest.result = 'Async request %s cast success, ' \
                                      'ctxt after function error~%s' % (rpc_method, e.message)
            else:
                asyncrequest.result = 'Async request %s cast success' % rpc_method
            finally:
                session.flush()

        request_id = asyncrequest.request_id
        finishtime = asyncrequest.finishtime
        deadline = asyncrequest.deadline + 1
        expire = asyncrequest.expire
        if expire:
            storage = get_cache()
        else:
            storage = session

        def check_respone():
            wait = finishtime - int(time.time())
            # 先等待3秒,可以做一次提前检查
            if wait > 3:
                eventlet.sleep(3)
            no_response_agents = set(wait_agents)
            interval = int(wait / 10)
            if interval < 3:
                interval = 3
            elif interval > 10:
                interval = 10
            not_overtime = 2
            while True:
                no_response_agents = responeutils.norespones(storage=storage,
                                                             request_id=request_id,
                                                             agents=no_response_agents)
                if not no_response_agents:
                    break
                if int(time.time()) < finishtime:
                    eventlet.sleep(interval)
                if int(time.time()) > deadline:
                    not_overtime -= 1
                    if not not_overtime:
                        break
                eventlet.sleep(1)
            LOG.debug('Not response agents count %d' % len(no_response_agents))
            bulk_data = []
            agent_time = int(time.time())
            for agent_id in no_response_agents:
                data = dict(request_id=request_id,
                            agent_id=agent_id,
                            agent_time=agent_time,
                            resultcode=manager_common.RESULT_OVER_FINISHTIME,
                            result='Agent respone overtime')
                bulk_data.append(data)
            responeutils.bluk_insert(storage, no_response_agents, bulk_data, expire)
            asyncrequest.status = manager_common.FINISH
            if no_response_agents:
                asyncrequest.resultcode = manager_common.RESULT_NOT_ALL_SUCCESS
                asyncrequest.result = 'agents not respone, count:%d' % len(no_response_agents)
            else:
                asyncrequest.resultcode = manager_common.RESULT_SUCCESS
                asyncrequest.result = 'all agent respone result'
            session.flush()
            if post_run:
                try:
                    post_run.run(asyncrequest, no_response_agents)
                except RpcServerCtxtException as e:
                    asyncrequest.result += ('ctxt post function error~%s' % e.message)
                    session.flush()
            session.close()

        threadpool.add_thread(safe_func_wrapper, check_respone, LOG)

    def rpc_changesource(self, ctxt, agent_id, fds, conns, free, process, cputime, iowait, left, metadata):
        """agent status of performance change"""
        if agent_id not in self.agents_loads:
            session = get_session(readonly=True)
            query = model_query(session, Agent, filter=Agent.agent_id == agent_id)
            agent = query.one_or_none()
            if not agent:
                return
            if agent_id not in self.agents_loads:
                self.agents_loads[agent_id] = dict(cpu=agent.cpu,
                                                   memory=agent.memory,
                                                   disk=agent.disk)
        new_status = {'free': free, 'process': process,
                      'cputime': cputime, 'iowait': iowait,
                      'left': left, 'fds': fds, 'conns': conns,
                      'time': int(time.time())}
        # 元数据为None时不更新元数据
        if metadata is not None:
            new_status['metadata'] = metadata
        else:
            # 当前agent没有元数据,尝试获取元数据
            if not self.agents_loads[agent_id].get('metadata'):
                # cache_store = get_redis()
                # metadata = cache_store.get(targetutils.host_online_key(agent_id))
                # new_status['metadata'] = metadata if not metadata else jsonutils.loads_as_bytes(metadata)
                global_data = get_global()
                metadatas = global_data.agents_metadata([agent_id, ])
                new_status['metadata'] = metadatas.get(agent_id)
        self.agents_loads[agent_id].update(new_status)

    def rpc_deletesource(self, ctxt, agent_id):
        """remove agent from change list"""
        self.agents_loads.pop(agent_id)

    def _sort_by_weigher(self, weighters, chioces):

        LOG.debug('Sort by weighters')
        if LOG.isEnabledFor(logging.DEBUG):
            LOG.debug('weighters %s' % str(weighters))
            LOG.debug('chioces %s' % str(chioces))
            need = [d.keys()[0] for d in weighters]
            for chioce in chioces:
                _loads = []
                loads = self.agents_loads[chioce]
                for key in need:
                    value = iter_value(loads, key)
                    _loads.append('%s:%s' % (str(key), str(value)))
                LOG.debug('chioce %d loads %s' % (chioce, ','.join(_loads)))

        def _weight(agent_id):
            loads = self.agents_loads[agent_id]
            sorts = []
            for weighter in weighters:
                target, _value = weighter.items()[0]
                value = iter_value(loads, target)
                if value is NOTFOUND:
                    raise InvalidArgument('weighter error, key not found')
                if not _value:
                    sorts.append(value)
                else:
                    sorts.append(value/_value)
            if LOG.isEnabledFor(logging.DEBUG):
                LOG.debug('sorts %s' % str(sorts))
            return sorts

        chioces.sort(key=_weight)

    def _exclud_filter(self, includes, chioces):
        LOG.debug('include filters')
        _includes = utils.include(includes)
        if LOG.isEnabledFor(logging.DEBUG):
            LOG.debug('includes %s' % str(includes))
        removes = set()
        for agent_id in chioces:
            include = False
            for target in _includes:
                include = True
                for baselines in _includes[target]:
                    if not include:
                        break
                    _operator, baseline = baselines
                    value = iter_value(self.agents_loads[agent_id], target)
                    if value is NOTFOUND:
                        include = False
                        break
                    if value is None:
                        value = 'None'
                    if not _operator(value, baseline):
                        include = False
                        break
                if not include:
                    break
            if not include:
                removes.add(agent_id)
        for agent_id in removes:
            chioces.remove(agent_id)
        removes.clear()

    def rpc_chioces(self, ctxt, target, includes=None, weighters=None):
        """chioce best best performance agent for endpoint"""
        session = get_session(readonly=True)
        query = session.query(Agent.agent_id).join(AgentEndpoint,
                                                   and_(Agent.agent_id == AgentEndpoint.agent_id,
                                                        AgentEndpoint.endpoint == target))
        # 可以选取的服务器列表
        chioces = []
        # 30分钟以内上报过数据的服务器才可以被选取
        timeline = int(time.time()) - (30*60 + 30)
        for agent in query:
            if agent.agent_id in self.agents_loads:
                loads = self.agents_loads[agent.agent_id]
                if loads.get('time') and loads.get('time') > timeline:
                    chioces.append(agent.agent_id)
        if not chioces:
            LOG.info('Not agent found for endpoint %s, maybe report overtime?' % target)
            return ChiocesResult(chioces)
        # 有包含规则
        if includes:
            self._exclud_filter(includes, chioces)
        if not chioces:
            LOG.info('Not agent found for endpoint %s with includes' % target)
            if LOG.isEnabledFor(logging.DEBUG):
                LOG.debug('No agent found includes %s', includes)
                LOG.debug('No agent found weighters %s', weighters)
            return ChiocesResult(chioces)
        # 没有排序规则
        if not weighters:
            # 统计agent的entitys数量
            query = model_query(session, (AgentEntity.agent_id, func.count(AgentEntity.id)),
                                filter=AgentEntity.agent_id.in_(chioces))
            query.group_by(AgentEntity.agent_id)
            count = {}
            for r in query:
                count[r[0]] = r[1]
            # 按照entitys数量排序
            chioces.sort(key=lambda agent_id: count.get(agent_id, 0))
        else:
            # 按照排序规则排序
            self._sort_by_weigher(weighters, chioces)
        return ChiocesResult(chioces)

        # def rpc_notify(self, ctxt, endpoint, entity,
        #                message, async=True, **kwargs):
        #     pass
