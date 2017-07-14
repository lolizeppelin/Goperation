import webob.exc

from sqlalchemy import func
from sqlalchemy.sql import or_
from sqlalchemy.sql import and_

from redis.exceptions import RedisError

from simpleutil.utils import argutils
from simpleutil.utils import timeutils
from simpleutil.utils import jsonutils

from simpleutil.log import log as logging

from simpleutil.utils.attributes import validators

from simpleutil.common.exceptions import InvalidArgument
from simpleutil.common.exceptions import InvalidInput


from simpleservice.ormdb.api import model_query
from simpleservice.ormdb.api import model_count_with_key
from simpleservice.ormdb.api import model_autoincrement_id
from simpleservice.rpc.driver.exceptions import MessagingTimeout
from simpleservice.rpc.driver.exceptions import ClientSendError


from goperation.plugin import utils

from goperation.plugin.manager import common as manager_common

from goperation.plugin.manager.models import Agent
from goperation.plugin.manager.models import AgentEndpoint

from goperation.plugin.manager import targetutils
from goperation.plugin.manager.wsgi import contorller
from goperation.plugin.manager.wsgi import resultutils
from goperation.plugin.manager.api import mlock
from goperation.plugin.manager.api import get_redis
from goperation.plugin.manager.api import get_client
from goperation.plugin.manager.api import get_session
from goperation.plugin.manager.api import rpcdeadline

from goperation.plugin.manager.rpc.exceptions import RPCResultError


from sqlalchemy.exc import OperationalError
from simpleservice.ormdb.exceptions import DBError
from simpleservice.rpc.driver.exceptions import NoSuchMethod

LOG = logging.getLogger(__name__)

FAULT_MAP = {InvalidArgument: webob.exc.HTTPClientError,
             NoSuchMethod: webob.exc.HTTPNotImplemented,
             MessagingTimeout: webob.exc.HTTPServiceUnavailable,
             RPCResultError: webob.exc.HTTPNotImplemented,
             ClientSendError: webob.exc.HTTPNotImplemented,
             }

Idformater = argutils.Idformater(key='agent_id', magic='all', formatfunc=int)


class AgentReuest(contorller.BaseContorller):

    def _all_id(self):
        _cache_server = get_redis()
        key = targetutils.agent_all_id()
        all_ids = _cache_server.smembers(key)
        if not all_ids:
            # lazy init all agent id cache
            with mlock(targetutils.lock_all_agent):
                session = get_session(readonly=True)
                query = session.query(Agent.agent_id).filter(Agent.status > manager_common.DELETED)
                for result in query:
                    if not _cache_server.sadd(key, str(result[0])):
                        # TODO error type should be replace
                        raise RuntimeError('Cant not add agent_id to redis, key %s' % key)
            all_ids = _cache_server.smembers(key)
            if not all_ids:
                return set()
        id_set = set()
        for agent_id in all_ids:
            id_set.add(int(agent_id))
        return id_set

    def check_agent_id(self, agent_id):
        if not isinstance(agent_id, set):
            id_set = set()
            id_set.add(agent_id)
            agent_id = id_set
        all_id = self.all_id
        if agent_id != all_id:
            for _id in agent_id:
                if _id not in all_id:
                    raise InvalidArgument('agent id %d can not be found'  % agent_id)

    def index(self, req, body):
        """call buy client"""
        filter_list = []
        session = get_session(readonly=True)
        agent_type = body.pop('agent_type', None)
        order = body.pop('order', None)
        desc = body.pop('desc', False)
        page_num = body.pop('page_num', 0)
        if agent_type:
            filter_list.append(Agent.agent_type == agent_type)
        deleted = body.pop('deleted', False)
        if not deleted:
            filter_list.append(Agent.status > manager_common.DELETED)

        agent_filter = and_(*filter_list)
        ret_dict = resultutils.bulk_results(session,
                                            model=Agent,
                                            columns=[Agent.agent_id,
                                                     Agent.agent_type,
                                                     Agent.status,
                                                     Agent.cpu,
                                                     Agent.memory,
                                                     Agent.disk,
                                                     Agent.entiy,
                                                     Agent.endpoints,
                                                     Agent.create_time,
                                                     ],
                                            counter=Agent.agent_id,
                                            order=order, desc=desc,
                                            filter=agent_filter, page_num=page_num)
        return ret_dict

    @argutils.Idformater(key='agent_id', formatfunc=int)
    def show(self, req, agent_id, body):
        """call buy client"""
        session = get_session(readonly=True)
        query = model_query(session, Agent)
        agent = query.filter_by(agent_id=agent_id).one_or_none()
        if not agent:
            raise InvalidArgument('Agent_id id:%s can not be found' % agent_id)
        result = resultutils.results(total=1, pagenum=0, result='Show agent success')
        result['data'].append(dict(agent_id=agent.agent_id,
                                   host=agent.host,
                                   status=agent.status,
                                   ports_range=agent.ports_range,
                                   endpoints=[v['endpoint'] for v in agent.endpoints],
                                   ))
        return result

    def create(self, req, body):
        """call bay agent"""
        new_agent = Agent()
        try:
            new_agent.host = validators['type:hostname'](body.pop('host'))
            new_agent.agent_type = body.pop('agent_type', None)
            if new_agent.agent_type is None or len(new_agent.agent_type) > 64:
                raise ValueError('Agent type info over size')
            new_agent.ports_range = jsonutils.dumps(validators['type:ports_range_list'](body.pop('ports_range')))
            if len(new_agent.ports_range) > manager_common.MAX_PORTS_RANGE_SIZE:
                raise ValueError('Ports range info over size')
            new_agent.memory = int(body.pop('memory'))
            new_agent.cpu = int(body.pop('cpu'))
            new_agent.disk = int(body.pop('disk'))
            endpoints = utils.validate_endpoints(body.pop('endpoints', []))
        except KeyError as e:
            raise InvalidArgument('Can not find argument: %s' % e.message)
        except ValueError as e:
            raise InvalidArgument('Argument value type error: %s' % e.message)
        new_agent.create_time = timeutils.realnow()
        new_agent.entiy = 0
        if endpoints:
            endpoints_entitys = []
            for endpoint in endpoints:
                endpoints_entitys.append(AgentEndpoint(endpoint=endpoint))
            new_agent.endpoints = endpoints_entitys
        session = get_session()
        _cache_server = get_redis()
        with mlock(targetutils.lock_all_agent):
            host_filter = and_(Agent.host == new_agent.host, Agent.status > manager_common.DELETED)
            if model_count_with_key(session, Agent.host, filter=host_filter) > 0:
                raise InvalidArgument('Duplicate host %s exist' % new_agent.host)
            with session.begin(subtransactions=True):
                new_agent_id = model_autoincrement_id(session, Agent.agent_id)
                new_agent.agent_id = new_agent_id
                session.add(new_agent)
                result = resultutils.results(total=1, pagenum=0, result='Create agent success',
                                             data=[dict(agent_id=new_agent.agent_id,
                                                        host=new_agent.host,
                                                        status=new_agent.status,
                                                        ports_range=new_agent.ports_range,
                                                        endpoints=endpoints)
                                                   ])
                key = targetutils.agent_all_id()
                if not _cache_server.sadd(key, str(new_agent.agent_id)):
                    # TODO error type shoud be replace
                    raise RuntimeError('Cant not add agent_id to redis, key %s' % key)
                return result

    @argutils.Idformater(key='agent_id', formatfunc=int)
    def delete(self, req, agent_id, body):
        """call buy client"""
        # if force is true
        # will not notify agent, just delete agent from database
        force = body.get('force', False)
        if not force:
            _cache_server = get_redis()
            rpc = get_client()
        session = get_session()
        query = model_query(session, Agent,
                            filter=and_(Agent.agent_id == agent_id,
                                        Agent.status > manager_common.DELETED))
        with mlock(targetutils.AgentLock(agent_id)):
            with session.begin(subtransactions=True):
                agent = query.one_or_none()
                if not agent:
                    raise InvalidArgument('Can not find agent with %d, not exist or alreay deleted' % agent_id)
                if agent.entiy > 0:
                    raise InvalidArgument('Can not delete agent, entiy not 0')
                if not force:
                    host_online_key = targetutils.host_online_key(agent.agent_id)
                    # make sure agent is online
                    agent_ipaddr = _cache_server.get(host_online_key)
                    if agent_ipaddr is None:
                        raise ClientSendError(str(agent_id), 'Can not delete offline agent, try force')
                    # tell agent wait delete
                    delete_agent_precommit = rpc.call(targetutils.target_agent(agent),
                                                      ctxt={'deadline': rpcdeadline()},
                                                      msg={'method': 'delete_agent_precommit',
                                                           'args': {'agent_id': agent.agent_id,
                                                                    'agent_type': agent.agent_type,
                                                                    'host': agent.host,
                                                                    'ipaddr': agent_ipaddr}
                                                            })
                    if not delete_agent_precommit:
                        raise RPCResultError('delete_agent_precommit result is None')
                    if delete_agent_precommit.get('resultcode') != manager_common.RESULT_SUCCESS:
                        return resultutils.results(total=1, pagenum=0,
                                                   result=delete_agent_precommit.get('result'), resultcode=1)
                # Mark agent deleted
                query.update({'status': manager_common.DELETED})
                # Delete endpoint of agent
                query = model_query(session, AgentEndpoint,
                                    filter=AgentEndpoint.agent_id == agent_id)
                try:
                    query.delete()
                except OperationalError as e:
                    LOG.error("Delete agent endpoint error:%d, %s" %
                              (e.orig[0], e.orig[1].replace("'", '')))
                    raise
                except DBError as e:
                    LOG.error("Delete agent endpoint DBError:%s" % e.message)
                    raise
                if not force:
                    # tell agent delete itself
                    delete_agent_postcommit = rpc.call(targetutils.target_agent(agent),
                                                       ctxt={'deadline': rpcdeadline()},
                                                       msg={'method': 'delete_agent_postcommit',
                                                            'args': {'agent_id': agent.agent_id,
                                                                     'agent_type': agent.agent_type,
                                                                     'host': agent.host,
                                                                     'ipaddr': agent_ipaddr}
                                                            })
                    if not delete_agent_postcommit:
                        raise RPCResultError('delete_agent_postcommit result is None')
                    if delete_agent_postcommit.get('resultcode') != manager_common.RESULT_SUCCESS:
                        raise RPCResultError('Call agent delete fail: ' + delete_agent_postcommit.get('result'))
                result = resultutils.results(total=1, pagenum=0, result='Delete agent success',
                                             data=[dict(agent_id=agent.agent_id,
                                                        host=agent.host,
                                                        status=agent.status,
                                                        ports_range=agent.ports_range)
                                                   ])
                key = targetutils.agent_all_id()
                if not _cache_server.srem(key, str(agent_id.agent_id)):
                    LOG.error('Remove agent_id from redis fail, key %s' % key)
                return result

    @argutils.Idformater(key='agent_id', formatfunc=int)
    def status(self, req, agent_id, body):
        """get status from agent, not from database"""
        persist = body.pop('persist', 0)
        session = get_session(readonly=True)
        rpc = get_client()
        _cache_server = get_redis()
        query = model_query(session, Agent, filter=Agent.agent_id == agent_id)
        agent = query.one_or_none()
        if not agent:
            raise InvalidArgument('Agent_id id:%s can not be found' % agent_id)
        host_online_key = targetutils.host_online_key(agent.agent_id)
        # make sure agent is online
        agent_ipaddr = _cache_server.get(host_online_key)
        if agent_ipaddr is None:
            raise ClientSendError(str(agent_id), 'Can not get status from offline agent')
        status_agent = rpc.call(targetutils.target_agent(agent),
                                ctxt={'deadline': rpcdeadline(),
                                      'persist': persist},
                                msg={'method': 'status_agent',
                                     'args': {'agent_id': agent.agent_id,
                                              'agent_type': agent.agent_type,
                                              'host': agent.host,
                                              'ipaddr': agent_ipaddr}.update(body)
                                     })
        if not status_agent:
            raise RPCResultError('status_agent result is None')
        result = resultutils.results(resultcode=status_agent.pop('resultcode'),
                                     result=status_agent.pop('result'),
                                     data=[dict(agent_id=agent.agent_id,
                                                host=agent.host,
                                                status=agent.status).update(status_agent)
                                           ])
        return result

    @Idformater
    def update(self, req, agent_id, body):
        """call by agent"""
        session = get_session()
        with mlock(targetutils.lock_all_agent) as lock:
            query = model_query(session, Agent, filter=(Agent.status > manager_common.DELETED))
            if len(agent_id) < len(self.all_id):
                query = query.filter(Agent.agent_id.in_(agent_id))
                # degrade lock level
                lock.degrade([targetutils.AgentLock(_id) for _id in agent_id])
            data = body
            if not data:
                raise InvalidInput('Not data exist')
            with session.begin(subtransactions=True):
                query.update(data)
            result = resultutils.results(total=len(agent_id), pagenum=0,
                                         result='Update agent success',
                                         data=[body, ])
            return result

    @Idformater
    def active(self, req, agent_id, body):
        """call buy client"""
        _cache_server = get_redis()
        rpc = get_client()
        session = get_session()
        query = model_query(session, Agent,
                            filter=and_(Agent.agent_id == agent_id,
                                        Agent.status > manager_common.DELETED))
        agent = query.one_or_none()
        if not agent:
            raise InvalidArgument('Agent_id id:%s can not be found' % agent_id)
        host_online_key = targetutils.host_online_key(agent.agent_id)
        # make sure agent is online
        agent_ipaddr = _cache_server.get(host_online_key)
        if agent_ipaddr is None:
            raise ClientSendError(str(agent_id), 'Can not active offline agent')
        with session.begin(subtransactions=True):
            query.update({'status': manager_common.ACTIVE})
            active_agent = rpc.call(targetutils.target_server(agent.agent_type, agent.host),
                                    ctxt={'deadline': rpcdeadline()},
                                    msg={'method': 'active_agent',
                                         'args': {'agent_id': agent_id,
                                                  'agent_ipaddr': agent_ipaddr}
                                         })
            if not active_agent:
                raise RPCResultError('active_agent result is None')
            if active_agent.pop('resultcode') != manager_common.RESULT_SUCCESS:
                raise RPCResultError('Call agent active fail: ' + active_agent.get('result'))
            result = resultutils.results(result=active_agent.pop('result'),
                                         data=[dict(agent_id=agent.agent_id,
                                                    host=agent.host,
                                                    ipaddr=agent_ipaddr,
                                                    status=agent.status).update(active_agent)
                                               ])
            return result

    @Idformater
    def upgrade(self, req, agent_id, body):
        """call by client, and asyncrequest
        send rpm file to upgrade code of agent
        """
        md5 = body.pop('md5', None)
        crc32 = body.pop('crc32', None)
        url = body.pop('url', None)
        if not crc32 and not md5 and not url:
            raise InvalidArgument('update file must be set, need md5 or crc32 or url')
        force = body.pop('force', False)
        session = get_session(readonly=True)
        rpc = get_client()
        with mlock(targetutils.lock_all_agent) as lock:
            self.check_agent_id(agent_id)
            if len(agent_id) < len(self.all_id):
                lock.degrade([targetutils.AgentLock(_id) for _id in agent_id])
            rpc.cast(targetutils.target_all(),
                     ctxt={'deadline': rpcdeadline()},
                     msg={'method': 'upgrade_agent_precommit',
                          'args': {'agent_id': agent_id,
                                   'md5': md5,
                                   'crc32': crc32,
                                   'url': url,
                                   'force': force}
                          })
            asyncrequest = self.create_asyncrequest(req, body)
            asyncrequest.result = \
                'upgrade agent method has send, wait %d agent respone' % len(agent_id)
            with session.begin(subtransactions=True):
                session.add(asyncrequest)
                rpc.cast(targetutils.target_all(),
                         ctxt={'deadline': rpcdeadline()},
                         msg={'method': 'upgrade_agent_postcommit',
                              'args': {'agent_id': agent_id,
                                       'md5': md5,
                                       'crc32': crc32,
                                       'url': url,
                                       'force': force}
                              })
        rpc.cast(targetutils.target_anyone(manager_common.SCHEDULER),
                 ctxt={'finishtime': asyncrequest.finishtime,
                       'deadline': asyncrequest.deadline,
                       'persist': 1},
                 msg={'method': 'async_request_check',
                      'args': {'domain': '',
                               'request_id': asyncrequest.request_id,
                               'agent_id': agent_id}
                      })
        return resultutils.results(result=asyncrequest.result)

    def online(self, req, body):
        """call buy agent
        when a agent start, it will call online to show it's ipaddr
        and get agent_id from gcenter
        """
        try:
            host = validators['type:hostname'](body.pop('host'))
            agent_type = body.pop('agent_type', 'nonetype')
            agent_ipaddr = validators['type:ip_address'](body.pop('agent_ipaddr'))
        except KeyError as e:
            raise InvalidArgument('Can not find argument: %s' % e.message)
        except ValueError as e:
            raise InvalidArgument('Argument value type error: %s' % e.message)
        except InvalidInput as e:
            raise InvalidArgument(e.message)
        session = get_session(readonly=True)
        _cache_server = get_redis()
        query = model_query(session, Agent,
                            filter=(and_(Agent.status > manager_common.DELETED,
                                         Agent.agent_type == agent_type, Agent.host == host)))
        # with mlock(targetutils.lock_all_agent) as lock:
        agent = query.one_or_none()
        if not agent:
            LOG.info('Online called but no Agent found')
            ret = {'agent_id': None}
        else:
            LOG.info('Agent online called. agent_id:%(agent_id)s, type:%(agent_type)s, '
                     'host:%(host)s, ipaddr:%(agent_ipaddr)s' %
                     {'agent_id': agent.agent_id,
                      'agent_type': agent_type,
                      'host': host,
                      'agent_ipaddr': agent_ipaddr})
            # lock.degrade([targetutils.AgentLock(agent.agent_id)])
            ret = {'agent_id': agent.agent_id, 'status': agent.status}
            host_online_key = targetutils.host_online_key(agent.agent_id)
            exist_host_ipaddr = _cache_server.get(host_online_key)
            if exist_host_ipaddr is not None:
                if exist_host_ipaddr != agent_ipaddr:
                    LOG.error('Host call online with %s, but %s alreday exist on redis' %
                              (agent_ipaddr, exist_host_ipaddr))
                    raise InvalidArgument('Host %s with ipaddr %s alreday eixst' % (host, exist_host_ipaddr))
                # key exist, set new expire time
                if not _cache_server.expire(host_online_key,
                                            manager_common.ONLINE_EXIST_TIME):
                    if not _cache_server.set(host_online_key, agent_ipaddr,
                                             ex=manager_common.ONLINE_EXIST_TIME, nx=True):
                        raise InvalidArgument('Another agent login with same '
                                              'host or someone set key %s' % host_online_key)
            else:
                if not _cache_server.set(host_online_key, agent_ipaddr,
                                         ex=manager_common.ONLINE_EXIST_TIME, nx=True):
                    raise InvalidArgument('Another agent login with same host or someone set key %s' %
                                          host_online_key)
        result = resultutils.results(total=1, pagenum=0, result='Online agent function run success')
        result['data'].append(ret)
        return result

    @Idformater
    def file(self, req, agent_id, body):
        """call by client, and asyncrequest
        send file to agents
        """
        # self.create_asyncrequest(req, body)
        # agent_type = body.get('agent_type', None)
        # method = body.get('method')
        # host = body.get('host')
        # path = body.get('path')
        # rpc = get_client()
        # if agent_type:
        #     cast_ret = rpc.cast(target=targetutils.target_alltype(agent_type))
        # else:
        #     cast_ret = rpc.cast(target=targetutils.target_all())
        # call_ret = rpc.call(target='')