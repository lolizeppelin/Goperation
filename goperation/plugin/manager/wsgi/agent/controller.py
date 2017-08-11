import webob.exc

from sqlalchemy.sql import and_

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
from simpleservice.rpc.driver.exceptions import RpcClientSendError


from goperation.plugin import utils

from goperation.plugin.manager import common as manager_common

from goperation.plugin.manager.models import Agent
from goperation.plugin.manager.models import AgentEndpoint
from goperation.plugin.manager.models import AllocatedPort

from goperation.plugin.manager import targetutils
from goperation.plugin.manager import goplockutils
from goperation.plugin.manager.wsgi import contorller
from goperation.plugin.manager.wsgi import resultutils
from goperation.plugin.manager.api import mlock
from goperation.plugin.manager.api import get_cache
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
             RPCResultError: webob.exc.HTTPInternalServerError,
             RpcClientSendError: webob.exc.HTTPInternalServerError,
             }

Idformater = argutils.Idformater(key='agent_id', formatfunc='agents_id_check')


class AgentReuest(contorller.BaseContorller):

    def _all_id(self):
        _cache_server = get_redis()
        key = targetutils.agent_all_id()
        all_ids = _cache_server.smembers(key)
        if not all_ids:
            # lazy init all agent id cache
            session = get_session(readonly=True)
            with mlock(goplockutils.lock_all_agent):
                query = session.query(Agent.agent_id).filter(Agent.status > manager_common.DELETED)
                ADDED = False
                for result in query:
                    ADDED = True
                    if not _cache_server.sadd(key, str(result[0])):
                        # TODO error type should be replace
                        raise RuntimeError('Cant not add agent_id to redis, key %s' % key)
                if not ADDED:
                    return set()
            all_ids = _cache_server.smembers(key)
            if not all_ids:
                raise RuntimeError('Add agent_id to redis success, but get from redis is empyt')
        id_set = set()
        for agent_id in all_ids:
            id_set.add(int(agent_id))
        return id_set

    def agents_id_check(self, agents_id):
        if agents_id == 'all':
            return self._all_id()
        agents_set = argutils.map_to_int(agents_id)
        all_id = self._all_id()
        if agents_set != all_id:
            for _id in agents_set:
                if _id not in all_id:
                    raise InvalidArgument('agent id %d can not be found'  % _id)
        return agents_set

    def agent_id_check(self, agent_id):
        """For one agent"""
        if agent_id == 'all':
            raise InvalidArgument('Just for one agent')
        agent_id = self.agents_id_check(agent_id)
        if len(agent_id) > 1:
            raise InvalidArgument('Just for one agent')
        return agent_id.pop()

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

    @argutils.Idformater(key='agent_id', formatfunc='agent_id_check')
    def show(self, req, agent_id, body):
        """call buy client"""
        session = get_session(readonly=True)
        query = model_query(session, Agent)
        agent = query.filter_by(agent_id=agent_id).one_or_none()
        if not agent:
            return resultutils.results(resultcode=1,
                                       result='Agent_id id:%s can not be found' % agent_id)
        result = resultutils.results(total=1, pagenum=0, result='Show agent success')
        result['data'].append(dict(agent_id=agent.agent_id,
                                   host=agent.host,
                                   status=agent.status,
                                   ports_range=agent.ports_range,
                                   ports=[v.to_dict() for v in agent.ports],
                                   endpoints=[v['endpoint'] for v in agent.endpoints],
                                   ))
        return result

    def create(self, req, body):
        """call by agent in the normal case"""
        new_agent = Agent()
        try:
            new_agent.host = validators['type:hostname'](body.pop('host'))
            new_agent.agent_type = body.pop('agent_type', None)
            if new_agent.agent_type is None or len(new_agent.agent_type) > 64:
                raise ValueError('Agent type info over size')
            new_agent.ports_range = jsonutils.dump_as_bytes(validators['type:ports_range'](body.pop('ports_range')))
            new_agent.memory = int(body.pop('memory'))
            new_agent.cpu = int(body.pop('cpu'))
            new_agent.disk = int(body.pop('disk'))
            endpoints = utils.validate_endpoints(body.pop('endpoints', []))
        except KeyError as e:
            raise InvalidArgument('Can not find argument: %s' % e.message)
        except ValueError as e:
            raise InvalidArgument('Argument value type error: %s' % e.message)
        new_agent.create_time = timeutils.realnow()
        if endpoints:
            endpoints_entitys = []
            for endpoint in endpoints:
                endpoints_entitys.append(AgentEndpoint(endpoint=endpoint))
            new_agent.endpoints = endpoints_entitys
        session = get_session()
        _cache_server = get_cache()
        with mlock(goplockutils.lock_all_agent):
            host_filter = and_(Agent.host == new_agent.host, Agent.status > manager_common.DELETED)
            if model_count_with_key(session, Agent.host, filter=host_filter) > 0:
                result = resultutils.results(resultcode=manager_common.RESULT_ERROR,
                                             result='Create agent fail, host all ready exist with other id')
                return result
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
                # add new agent_id to cache all agent_id
                if not _cache_server.sadd(key, str(new_agent.agent_id)):
                    # TODO error type shoud be replace
                    raise RuntimeError('Cant not add agent_id to redis, key %s' % key)
                return result

    @argutils.Idformater(key='agent_id', formatfunc='agent_id_check')
    def delete(self, req, agent_id, body):
        """call buy agent"""
        # if force is true
        # will not notify agent, just delete agent from database
        force = body.get('force', False)
        if not force:
            _cache_server = get_cache()
            rpc = get_client()
        session = get_session()
        query = model_query(session, Agent,
                            filter=and_(Agent.agent_id == agent_id,
                                        Agent.status > manager_common.DELETED))
        with mlock(goplockutils.AgentLock(agent_id)):
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
                        raise RpcClientSendError(str(agent_id), 'Can not delete offline agent, try force')
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
                                                   result=delete_agent_precommit.get('result'),
                                                   resultcode=manager_common.RESULT_SUCCESS)
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

    @Idformater
    def status(self, req, agent_id, body):
        """get status from agent, not from database"""
        rpc = get_client()
        session = get_session()
        asyncrequest = self.create_asyncrequest(req, body)
        asyncrequest.result = \
            'status agent method has send, wait %d agent respone' % len(agent_id)
        agent_id = list(agent_id)
        with session.begin(subtransactions=True):
            session.add(asyncrequest)
            send_args = {'agent_id': agent_id}
            send_args.update(body)
            rpc.cast(targetutils.target_all(fanout=True),
                     ctxt={'deadline': asyncrequest.deadline,
                           'persist': asyncrequest.persist,
                           'request_id': asyncrequest.request_id},
                     msg={'method': 'status_agent',
                          'args': send_args
                          })
        try:
            rpc.cast(targetutils.target_anyone(manager_common.SCHEDULER),
                     ctxt={'deadline': asyncrequest.deadline},
                     msg={'method': 'async_request_check',
                          'args': {'agent_id': agent_id, 'request_id': asyncrequest.request_id,
                                   'deadline': asyncrequest.deadline,
                                   'finishtime': asyncrequest.finishtime,
                                   }
                          })
        except RpcClientSendError:
            LOG.warning('Send to scheduler check agent status fail')
        return resultutils.results(result=asyncrequest.result, data=[dict(request_id=asyncrequest.request_id,
                                                                          request_time=asyncrequest.request_time,
                                                                          finishtime=asyncrequest.finishtime,
                                                                          deadline=asyncrequest.deadline,
                                                                          )])

    @Idformater
    def update(self, req, agent_id, body):
        raise NotImplementedError

    @argutils.Idformater(key='agent_id', formatfunc='agent_id_check')
    def edit(self, req, agent_id, body):
        """call by agent"""
        # TODO  check data in body
        session = get_session()
        with mlock(goplockutils.AgentLock(agent_id)):
            query = model_query(session, Agent, filter=(and_(Agent.agent_id == agent_id,
                                                             Agent.status > manager_common.DELETED)))
            data = body
            if not data:
                raise InvalidInput('Not data exist')
            with session.begin(subtransactions=True):
                query.update(data)
            result = resultutils.results(total=len(agent_id), pagenum=0,
                                         result='Update agent success',
                                         data=[body, ])
            return result

    @argutils.Idformater(key='agent_id', formatfunc='agent_id_check')
    def active(self, req, agent_id, body):
        """call buy client"""
        status = body.get('status', manager_common.ACTIVE)
        if status not in (manager_common.ACTIVE, manager_common.UNACTIVE):
            raise InvalidArgument('Argument status not right')
        _cache_server = get_cache()
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
            raise RpcClientSendError(str(agent_id), 'Can not active or unactive a offline agent')
        with session.begin(subtransactions=True):
            agent.update({'status': status})
            active_agent = rpc.call(targetutils.target_server(agent.agent_type, agent.host),
                                    ctxt={'deadline': rpcdeadline()},
                                    msg={'method': 'active_agent',
                                         'args': {'agent_id': agent_id,
                                                  'agent_ipaddr': agent_ipaddr}
                                         })
            if not active_agent:
                raise RPCResultError('active_agent result is None')
            if active_agent.pop('resultcode') != manager_common.RESULT_SUCCESS:
                raise RPCResultError('Call agent active or unactive fail: ' + active_agent.get('result'))
            result = resultutils.results(result=active_agent.pop('result'),
                                         data=[dict(agent_id=agent.agent_id,
                                                    host=agent.host,
                                                    ipaddr=agent_ipaddr,
                                                    status=agent.status)
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
        session = get_session()
        rpc = get_client()
        with mlock(goplockutils.lock_all_agent):
            agent_id = list(agent_id)
            asyncrequest = self.create_asyncrequest(req, body)
            asyncrequest.result = \
                'upgrade agent method has send, wait %d agent respone' % len(agent_id)
            with session.begin(subtransactions=True):
                session.add(asyncrequest)
                rpc.cast(targetutils.target_all(fanout=True),
                         ctxt={'deadline': asyncrequest.deadline,
                               'request_id': asyncrequest.request_id},
                         msg={'method': 'upgrade_agent',
                              'args': {'agent_id': agent_id,
                                       'md5': md5,
                                       'crc32': crc32,
                                       'url': url,
                                       'force': force}
                              })
        try:
            rpc.cast(targetutils.target_anyone(manager_common.SCHEDULER),
                     ctxt={'deadline': asyncrequest.deadline},
                     msg={'method': 'async_request_check',
                          'args': {'agent_id': list(agent_id), 'request_id': asyncrequest.request_id,
                                   'deadline': asyncrequest.deadline,
                                   'finishtime': asyncrequest.finishtime,
                                   }
                          })
        except RpcClientSendError:
            LOG.warning('Send to SCHEDULER check agent upgrade fail')
        return resultutils.results(result=asyncrequest.result, data=[dict(request_id=asyncrequest.request_id,
                                                                          request_time=asyncrequest.request_time,
                                                                          finishtime=asyncrequest.finishtime,
                                                                          deadline=asyncrequest.deadline,
                                                                          )])

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
        _cache_server = get_cache()
        query = model_query(session, Agent,
                            filter=(and_(Agent.status > manager_common.DELETED,
                                         Agent.agent_type == agent_type, Agent.host == host)))
        agent = query.one_or_none()
        if not agent:
            LOG.info('Online called but no Agent found')
            ret = {'agent_id': None}
        else:
            LOG.debug('Agent online called. agent_id:%(agent_id)s, type:%(agent_type)s, '
                      'host:%(host)s, ipaddr:%(agent_ipaddr)s' %
                      {'agent_id': agent.agent_id,
                       'agent_type': agent_type,
                       'host': host,
                       'agent_ipaddr': agent_ipaddr})
            # lock.degrade([targetutils.AgentLock(agent.agent_id)])
            ret = {'agent_id': agent.agent_id}
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
                    raise InvalidArgument('Another agent login with same host or '
                                          'someone set key %s' % host_online_key)
        result = resultutils.results(result='Online agent function run success')
        result['data'].append(ret)
        return result

    @Idformater
    def send_file(self, req, agent_id, body):
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

    @argutils.Idformater(key='agent_id', formatfunc='agent_id_check')
    def get_ports(self, req, agent_id, body):
        endpoint = body.get('endpoint', None)
        session = get_session(readonly=True)
        get_filter = (AllocatedPort.agent_id == agent_id)
        if endpoint:
            get_filter = and_(get_filter, AllocatedPort.endpoint == endpoint)
        query = model_query(session, AllocatedPort, filter=get_filter)
        with mlock(goplockutils.AgentLock(agent_id)):
            return resultutils.results(result='Get port for %d success' % agent_id,
                                       data=[dict(port=x.port, endpoint=x.endpoint, port_desc=x.port_desc)
                                             for x in query.all()])

    @argutils.Idformater(key='agent_id', formatfunc='agent_id_check')
    def add_ports(self, req, agent_id, body):
        ports = body.get('ports', None)
        endpoint = body.get('endpoint', None)
        if not ports:
            raise InvalidArgument('Ports is None for add ports')
        if not endpoint:
            raise InvalidArgument('Endpoint is None for add ports')
        if not isinstance(ports, list):
            ports = [ports, ]
        for port in ports:
            if not isinstance(port, (int, long)):
                raise InvalidArgument('Port in ports not int, can not edit ports')
            if not (0 <= port <= 65535):
                raise InvalidArgument('Port in ports over range, can not edit ports')
        session = get_session()
        with mlock(goplockutils.AgentLock(agent_id)):
            with session.begin(subtransactions=True):
                for port in ports:
                    session.add(AllocatedPort(agent_id=agent_id, port=port, endpoint=endpoint))
        return resultutils.results(result='edit ports success')

    @argutils.Idformater(key='agent_id', formatfunc='agent_id_check')
    def delete_ports(self, req, agent_id, body):
        ports = body.get('ports', None)
        strict = body.get('strict', True)
        if not ports:
            raise InvalidArgument('Ports is None for edit ports')
        if not isinstance(ports, list):
            ports = [ports, ]
        for port in ports:
            if not isinstance(port, (int, long)):
                raise InvalidArgument('Port in ports not int, can not edit ports')
            if not (0 <= port <= 65535):
                raise InvalidArgument('Port in ports over range, can not edit ports')
        session = get_session()
        with mlock(goplockutils.AgentLock(agent_id)):
            with session.begin(subtransactions=True):
                port_filter = and_(AllocatedPort.agent_id == agent_id, AllocatedPort.port.in_(ports))
                query = model_query(session, AllocatedPort, filter=port_filter)
                delete_count = query.delete()
                need_to_delete = len(ports)
                if delete_count != len(ports):
                    LOG.warning('Delete %d ports, but expect count is %d' % (delete_count, need_to_delete))
                    if strict:
                        raise InvalidArgument('Submit %d ports, but only %d ports found' %
                                              (len(ports), need_to_delete))
        return resultutils.results(result='edit ports success')
