# -*- coding:utf-8 -*-
import time
import six
import eventlet

from sqlalchemy import func
from sqlalchemy.sql import and_
from sqlalchemy.orm import joinedload

from simpleutil.config import cfg
from simpleutil.log import log as logging
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
from goperation.manager.models import AsyncRequest
from goperation.manager.models import AgentEndpoint
from goperation.manager.models import AgentEntity
from goperation.manager.models import Agent
from goperation.manager.utils import targetutils
from goperation.manager.utils import responeutils
from goperation.manager.utils import resultutils

from goperation.manager.rpc.server import utils

from goperation.manager.rpc.base import RpcManagerBase


LOG = logging.getLogger(__name__)

CONF = cfg.CONF

NONE = object()


class ChiocesResult(resultutils.ServerRpcResult):

    def __init__(self, chioces):
        super(ChiocesResult, self).__init__(host=CONF.host, resultcode=manager_common.RESULT_SUCCESS,
                                            result='chioces agents success')
        self.agents = [agent.agent_id for agent in chioces]

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


class RpcServerManager(RpcManagerBase):

    def __init__(self):
        super(RpcServerManager, self).__init__(target=targetutils.target_rpcserver(CONF.host, fanout=True))
        self.agents_loads = {}

    def pre_start(self, external_objects):
        super(RpcServerManager, self).pre_start(external_objects)

    def post_start(self):
        self.force_status(manager_common.ACTIVE)
        self.add_periodic_task(ExpiredAgentStatusTask(self))

    def full(self):
        if not self.is_active:
            return True
        with self.work_lock.priority(0):
            if self.status != manager_common.ACTIVE:
                return True
            if threadpool.pool.free() < 5:
                return True
        return False

    def rpc_asyncrequest(self, ctxt,
                         asyncrequest, rpc_target, rpc_method,
                         rpc_ctxt, rpc_args):
        """async respone check"""
        session = get_session()
        finishtime = ctxt.get('finishtime', None)
        asyncrequest = AsyncRequest(**asyncrequest)

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
            asyncrequest.result = 'Scheduler not active now'
            asyncrequest.status = manager_common.FINISH
            session.add(asyncrequest)
            session.flush()
            return

        if rpc_ctxt.get('agents') is None:
            wait_agents = [x[0] for x in model_query(session, Agent.agent_id,
                                                     filter=Agent.status > manager_common.DELETED).all()]
        else:
            wait_agents = rpc_ctxt.get('agents')
        rpc_ctxt.setdefault('request_id', asyncrequest.request_id)
        rpc_ctxt.setdefault('expire', asyncrequest.expire)

        target = Target(**rpc_target)
        rpc = get_client()
        try:
            rpc.cast(target, ctxt=rpc_ctxt, msg={'method': rpc_method, 'args': rpc_args})
        except AMQPDestinationNotFound:
            asyncrequest.resultcode = manager_common.SEND_FAIL
            asyncrequest.result = 'Async %s request send fail, AMQPDestinationNotFound' % rpc_method
            asyncrequest.status = manager_common.FINISH
            session.add(asyncrequest)
            session.flush()
            return

        LOG.debug('Cast %s to %s' % (asyncrequest.request_id, target.to_dict()))
        asyncrequest.result = 'Async request %s cast success' % rpc_method
        session.add(asyncrequest)
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
            if wait > 0:
                eventlet.sleep(wait)
            not_response_agents = set(wait_agents)

            not_overtime = 2
            while True:
                not_response_agents = responeutils.norespones(storage=storage,
                                                              request_id=request_id,
                                                              agents=not_response_agents)
                if not not_response_agents:
                    break
                if int(time.time()) > deadline:
                    not_overtime -= 1
                    if not not_overtime:
                        break
                eventlet.sleep(1)
            LOG.debug('Not response agents count %d' % len(not_response_agents))
            bulk_data = []
            agent_time = int(time.time())
            for agent_id in not_response_agents:
                data = dict(request_id=request_id,
                            agent_id=agent_id,
                            agent_time=agent_time,
                            resultcode=manager_common.RESULT_OVER_FINISHTIME,
                            result='Agent respone overtime')
                bulk_data.append(data)
            count = responeutils.bluk_insert(storage, bulk_data, expire)
            asyncrequest.status = manager_common.FINISH
            if count:
                asyncrequest.resultcode = manager_common.RESULT_NOT_ALL_SUCCESS
                asyncrequest.result = 'agents not respone, count:%d' % count
            else:
                asyncrequest.resultcode = manager_common.RESULT_SUCCESS
                asyncrequest.result = 'all agent respone result'
            session.flush()
            session.close()

        threadpool.add_thread(safe_func_wrapper, check_respone, LOG)

    def rpc_changesource(self, ctxt, agent_id, fds, conns, free, process, cputime, iowait, left, attributes):
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
                      'time': int(time.time()),
                      'attributes': attributes}
        self.agents_loads[agent_id].update(new_status)

    def rpc_deletesource(self, ctxt, agent_id):
        """remove agent from change list"""
        self.agents_loads.pop(agent_id)

    def _sort_by_weigher(self, chioces, weighters):

        def _weight(agent):
            loads = self.agents_loads[agent.agent_id]
            sorts = []
            for weighter in weighters:
                target, _value = six.iteritems(weighter)
                keys = target.split('.')
                value = loads
                for key in keys:
                    value = value.get(key, NONE)
                    if value is NONE:
                        raise InvalidArgument('weighter error, key not found')
                if not value:
                    sorts.append(_value)
                else:
                    sorts.append(_value/value)
            return sorts

        chioces.sort(key=_weight)

    def _exclud_filter(self, includes, chioces):
        _includes = utils.include(includes)
        for agent in chioces:
            include = False
            for target in _includes:
                _operator, match = _includes[target]
                keys = target.split('.')
                value = self.agents_loads[agent.agent_id]
                for key in keys:
                    value = value.get(key, NONE)
                    if value is NONE:
                        break
                if value is None:
                    value = 'None'
                if _operator(value, match):
                    include = True
            if not include:
                chioces.remove(agent)

    def rpc_chioces(self, ctxt, target, includes=None, weighters=None):
        """chioce best best performance agent for endpoint"""
        session = get_session(readonly=True)
        query = model_query(session, Agent,
                            filter=and_(Agent.status == manager_common.ACTIVE,
                                        AgentEndpoint.endpoint == target))
        query = query.options(joinedload(Agent.endpoints))
        # 可以选取的服务器列表
        chioces = []
        for agent in query:
            if agent.agent_id in self.agents_loads:
                chioces.append(agent)

        # 有包含规则
        if includes:
            self._exclud_filter(includes, chioces)
        # 没有排序规则
        if not weighters:
            # 统计agent的entitys数量
            query = model_query(session, (AgentEntity.agent_id, func.count(AgentEntity.id)),
                                filter=AgentEntity.agent_id.in_([agent.agent_id for agent in chioces]))
            query.group_by(AgentEntity.agent_id)
            count = {}
            for r in query:
                count[r[0]] = r[1]
            # 按照entitys数量排序
            chioces.sort(key=lambda agent: count.get(agent.agent_id, 0))
        else:
            # 按照排序规则排序
            self._sort_by_weigher(chioces, weighters)
        return ChiocesResult(chioces)
