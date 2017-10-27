import functools
import webob.exc

from sqlalchemy.sql import and_
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.orm.exc import MultipleResultsFound

from simpleutil.common.exceptions import InvalidArgument
from simpleutil.common.exceptions import InvalidInput
from simpleutil.log import log as logging
from simpleutil.utils import argutils
from simpleutil.utils import timeutils
from simpleutil.utils.attributes import validators

from simpleservice.ormdb.api import model_query
from simpleservice.ormdb.api import model_count_with_key
from simpleservice.rpc.exceptions import AMQPDestinationNotFound
from simpleservice.rpc.exceptions import MessagingTimeout
from simpleservice.rpc.exceptions import NoSuchMethod

from goperation.manager import common as manager_common
from goperation.manager import utils
from goperation.manager import resultutils
from goperation.manager import targetutils
from goperation.manager.api import get_client
from goperation.manager.api import get_redis
from goperation.manager.api import get_cache
from goperation.manager.api import get_global
from goperation.manager.api import get_session
from goperation.manager.api import rpcfinishtime
from goperation.manager.models import Agent
from goperation.manager.models import AgentEndpoint
from goperation.manager.models import AgentEntity
from goperation.manager.exceptions import CacheStoneError
from goperation.manager.exceptions import EndpointNotEmpty
from goperation.manager.wsgi import contorller
from goperation.manager.wsgi.exceptions import RpcPrepareError
from goperation.manager.wsgi.exceptions import RpcResultError


LOG = logging.getLogger(__name__)

FAULT_MAP = {InvalidArgument: webob.exc.HTTPClientError,
             NoSuchMethod: webob.exc.HTTPNotImplemented,
             AMQPDestinationNotFound: webob.exc.HTTPServiceUnavailable,
             MessagingTimeout: webob.exc.HTTPServiceUnavailable,
             RpcResultError: webob.exc.HTTPInternalServerError,
             CacheStoneError: webob.exc.HTTPInternalServerError,
             RpcPrepareError: webob.exc.HTTPInternalServerError,
             NoResultFound: webob.exc.HTTPNotFound,
             MultipleResultsFound: webob.exc.HTTPInternalServerError
             }

Idsformater = argutils.Idformater(key='agent_id', formatfunc='agents_id_check')
Idformater = argutils.Idformater(key='agent_id', formatfunc='agent_id_check')


class AgentReuest(contorller.BaseContorller):

    def index(self, req, body):
        """call buy client"""
        filter_list = []
        session = get_session(readonly=True)
        agent_type = body.pop('agent_type', None)
        order = body.pop('order', None)
        desc = body.pop('desc', False)
        deleted = body.pop('deleted', False)
        page_num = body.pop('page_num', 0)
        if agent_type:
            filter_list.append(Agent.agent_type == agent_type)
        if not deleted:
            filter_list.append(Agent.status > manager_common.DELETED)
        else:
            filter_list.append(Agent.status <= manager_common.DELETED)

        agent_filter = and_(*filter_list)
        ret_dict = resultutils.bulk_results(session,
                                            model=Agent,
                                            columns=[Agent.agent_id,
                                                     Agent.agent_type,
                                                     Agent.status,
                                                     Agent.cpu,
                                                     Agent.memory,
                                                     Agent.disk,
                                                     Agent.entity,
                                                     Agent.endpoints,
                                                     Agent.create_time],
                                            counter=Agent.agent_id,
                                            order=order, desc=desc,
                                            filter=agent_filter, page_num=page_num)
        return ret_dict

    @Idformater
    def show(self, req, agent_id, body):
        ports = body.get('ports', False)
        entitys = body.get('entitys', False)
        session = get_session(readonly=True)
        query = model_query(session, Agent)
        agent = query.filter_by(agent_id=agent_id).one()
        endpoints = {}
        for endpoint in agent.endpoints:
            endpoints[endpoint] = {}
        result = resultutils.results(total=1, pagenum=0, result='Show agent success')
        if entitys:
            for entity in agent.entitys:
                try:
                    endpoints[entity.endpoint]['entity'].append(entity.entity)
                except KeyError:
                     endpoints[entity.endpoint] = {'entity': [entity.entity]}
        if ports:
            for port in agent.ports:
                try:
                    endpoints[port.endpoint]['ports'].append(port.port)
                except KeyError:
                     endpoints[port.endpoint] = {'ports': [port.port]}
        result_data = dict(agent_id=agent.agent_id, host=agent.host,
                           status=agent.status, ports_range=agent.ports_range, endpoints=endpoints)
        result['data'].append(result_data)
        return result

    def create(self, req, body):
        """call by agent in the normal case"""
        new_agent = Agent()
        try:
            new_agent.host = validators['type:hostname'](body.pop('host'))
            new_agent.agent_type = body.pop('agent_type', None)
            if new_agent.agent_type is None or len(new_agent.agent_type) > 64:
                raise ValueError('Agent type info over size')
            new_agent.ports_range = body.pop('ports_range')
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
            endpoints_list = []
            for endpoint in endpoints:
                endpoints_list.append(AgentEndpoint(endpoint=endpoint))
            new_agent.endpoints = endpoints_list
        global_data = get_global()
        try:
            global_data.add_agent(new_agent)
        except:
            result = resultutils.results(resultcode=manager_common.RESULT_ERROR,
                                         result='Create agent fail, host all ready exist with other id')
            return result
        result = resultutils.results(total=1, pagenum=0, result='Create agent success',
                                     data=[dict(agent_id=new_agent.agent_id,
                                                host=new_agent.host,
                                                status=new_agent.status,
                                                ports_range=new_agent.ports_range,
                                                endpoints=endpoints)
                                           ])
        return result

    @Idformater
    def delete(self, req, agent_id, body):
        """call buy agent"""
        # if force is true
        # will not notify agent, just delete agent from database
        force = body.get('force', False)
        _cache_server = get_cache()
        rpc = get_client()
        global_data = get_global()
        with global_data.delete_agent(agent_id) as agent:
            if not force:
                host_online_key = targetutils.host_online_key(agent.agent_id)
                # make sure agent is online
                agent_ipaddr = _cache_server.get(host_online_key)
                if agent_ipaddr is None:
                    raise RpcPrepareError('Can not delete offline agent, try force')
                # tell agent wait delete
                delete_agent_precommit = rpc.call(targetutils.target_agent(agent),
                                                  ctxt={'finishtime': rpcfinishtime()},
                                                  msg={'method': 'delete_agent_precommit',
                                                       'args': {'agent_id': agent.agent_id,
                                                                'agent_type': agent.agent_type,
                                                                'host': agent.host,
                                                                'ipaddr': agent_ipaddr}
                                                       })
                if not delete_agent_precommit:
                    raise RpcResultError('delete_agent_precommit result is None')
                if delete_agent_precommit.get('resultcode') != manager_common.RESULT_SUCCESS:
                    return resultutils.results(total=1, pagenum=0,
                                               result=delete_agent_precommit.get('result'),
                                               resultcode=manager_common.RESULT_SUCCESS)
        if not force:
            # tell agent delete itself
            rpc.cast(targetutils.target_agent(agent),
                     ctxt={'finishtime': rpcfinishtime()},
                     msg={'method': 'delete_agent_postcommit',
                          'args': {'agent_id': agent.agent_id,
                                   'agent_type': agent.agent_type,
                                   'host': agent.host,
                                   'ipaddr': agent_ipaddr}})
        result = resultutils.results(total=1, pagenum=0, result='Delete agent success',
                                     data=[dict(agent_id=agent.agent_id,
                                                host=agent.host,
                                                status=agent.status,
                                                ports_range=agent.ports_range)
                                           ])
        return result

    def clean(self, req, agent_id, body):
        session = get_session()
        query = model_query(session, Agent,
                            filter=and_(Agent.agent_id == agent_id,
                                        Agent.status <= manager_common.DELETED))
        entity_query = model_query(session, AgentEntity.entity, filter=Agent.agent_id == agent_id)
        with session.begin(subtransactions=True):
            entitys = entity_query.all()
            if entitys:
                for entity in entitys:
                    LOG.error('Clean agent fail, entity %s:%d still on %s' %
                              (entity.endpoint, entity.entity, agent_id))
                raise EndpointNotEmpty('Clean agent %s fail, still has %d entitys' % (agent_id, len(entitys)))
            count = query.delete()
            LOG.info('Clean deleted agent %d, agent_id %s' % (count, agent_id))
            return resultutils.results(result='Clean deleted agent success')

    @Idsformater
    def update(self, req, agent_id, body):
        raise NotImplementedError

    @Idformater
    def active(self, req, agent_id, body):
        """call buy client"""
        status = body.get('status', manager_common.ACTIVE)
        if status not in (manager_common.ACTIVE, manager_common.UNACTIVE):
            raise InvalidArgument('Argument status not right')
        _cache_server = get_redis()
        rpc = get_client()
        session = get_session()
        query = model_query(session, Agent,
                            filter=and_(Agent.agent_id == agent_id,
                                        Agent.status > manager_common.DELETED))
        agent = query.one()
        host_online_key = targetutils.host_online_key(agent.agent_id)
        # make sure agent is online
        agent_ipaddr = _cache_server.get(host_online_key)
        if agent_ipaddr is None:
            raise RpcPrepareError('Can not active or unactive a offline agent: %d' % agent_id)
        with session.begin(subtransactions=True):
            agent.update({'status': status})
            active_agent = rpc.call(targetutils.target_agent(agent),
                                    ctxt={'finishtime': rpcfinishtime()},
                                    msg={'method': 'active_agent',
                                         'args': {'agent_id': agent_id,
                                                  'agent_ipaddr': agent_ipaddr,
                                                  'status': status}
                                         })
            if not active_agent:
                raise RpcResultError('Active agent rpc result is None')
            if active_agent.pop('resultcode') != manager_common.RESULT_SUCCESS:
                raise RpcResultError('Call agent active or unactive fail: ' + active_agent.get('result'))
            result = resultutils.results(result=active_agent.pop('result'),
                                         data=[dict(agent_id=agent.agent_id,
                                                    host=agent.host,
                                                    ipaddr=agent_ipaddr,
                                                    status=agent.status)
                                               ])
            return result

    def flush(self, req, body=None):
        """flush redis key storage"""
        _cache_server = get_cache()
        get_global().flush_all_agents()
        if body.get('online', False):
            glock = get_global().lock('all_agents')
            with glock():
                # clean host online key
                keys = _cache_server.keys(targetutils.host_online_key('*'))
                if keys:
                    with _cache_server.pipeline() as pipe:
                        pipe.multi()
                        for key in keys:
                            pipe.delete(key)
                        pipe.execute()
        return resultutils.results(result='Delete cache id success')

    @Idformater
    def edit(self, req, agent_id, body):
        """call by agent"""
        # TODO  check data in body
        session = get_session()
        glock = get_global().lock('agents')
        with glock([agent_id, ]) as agents:
            agent = agents[0]
            data = body
            if not data:
                raise InvalidInput('Not data exist')
            with session.begin(subtransactions=True):
                agent.update(data)
            result = resultutils.results(pagenum=0,
                                         result='Update agent success',
                                         data=[body, ])
            return result

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

    @Idsformater
    def status(self, req, agent_id, body):
        """get status from agent, not from database
        do not need Idsformater, check it in send_asyncrequest
        """
        target = targetutils.target_all(fanout=True)
        rpc_method = 'status_agent'
        rpc_ctxt = {'agents': agent_id}
        rpc_args = body
        return self.send_asyncrequest(body, target, rpc_method, rpc_ctxt, rpc_args)

    def upgrade(self, req, agent_id, body):
        """call by client, and asyncrequest
        do not need Idsformater, check it in send_asyncrequest
        send rpm file to upgrade code of agent
        """
        md5 = body.pop('md5', None)
        crc32 = body.pop('crc32', None)
        uuid = body.pop('uuid', None)
        force = body.pop('force', False)
        asyncrequest = self.create_asyncrequest(body)
        if not crc32 and not md5 and not uuid:
            raise InvalidArgument('update file must be set, need md5 or crc32 or url')
        target = targetutils.target_all(fanout=True)
        rpc_method = 'upgrade_agent'
        rpc_args = {'md5': md5, 'crc32': crc32, 'uuid': uuid, 'force': force}
        glock = get_global().lock('agents')
        if agent_id == 'all':
            lock = glock.all_agent
        else:
            lock = functools.partial(glock.agents, agent_id)
        return self.send_asyncrequest(asyncrequest, target, rpc_method, rpc_args, lock)
