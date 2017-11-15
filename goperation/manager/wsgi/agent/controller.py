import functools
import webob.exc

from sqlalchemy.sql import and_
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.orm.exc import MultipleResultsFound

from simpleutil.common.exceptions import InvalidArgument
from simpleutil.common.exceptions import InvalidInput
from simpleutil.log import log as logging
from simpleutil.utils import jsonutils
from simpleutil.utils import uuidutils
from simpleutil.utils import singleton
from simpleutil.utils.attributes import validators

from simpleservice.ormdb.api import model_query
from simpleservice.rpc.exceptions import AMQPDestinationNotFound
from simpleservice.rpc.exceptions import MessagingTimeout
from simpleservice.rpc.exceptions import NoSuchMethod

from goperation import threadpool
from goperation.utils import safe_func_wrapper
from goperation.manager import common as manager_common
from goperation.manager import resultutils
from goperation.manager import targetutils
from goperation.manager.api import get_client
from goperation.manager.api import get_cache
from goperation.manager.api import get_global
from goperation.manager.api import get_session
from goperation.manager.api import rpcfinishtime
from goperation.manager.models import Agent
from goperation.manager.models import AgentEndpoint
from goperation.manager.models import AgentEntity
from goperation.manager.exceptions import CacheStoneError
from goperation.manager.exceptions import AgentHostExist
from goperation.manager.exceptions import EndpointNotEmpty
from goperation.manager.wsgi.contorller import BaseContorller
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


@singleton.singleton
class AgentReuest(BaseContorller):

    def index(self, req, body=None):
        """call buy client"""
        body = body or {}
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
                                                     # Agent.entitys,
                                                     Agent.endpoints,
                                                     Agent.create_time],
                                            counter=Agent.agent_id,
                                            order=order, desc=desc,
                                            filter=agent_filter, page_num=page_num)
        return ret_dict

    @BaseContorller.AgentIdformater
    def show(self, req, agent_id, body=None):
        body = body or {}
        show_ports = body.get('ports', False)
        show_entitys = body.get('entitys', False)
        session = get_session(readonly=True)
        joins = joinedload(Agent.endpoints, innerjoin=False)
        if show_entitys:
            joins = joins.joinedload(AgentEndpoint.entitys, innerjoin=False)
        if show_ports:
            joins = joins.joinedload(AgentEntity.ports, innerjoin=False)
        query = model_query(session, Agent).options(joins)
        agent = query.filter_by(agent_id=agent_id).one()
        result = resultutils.results(total=1, pagenum=0, result='Show agent success')
        endpoints = {}
        for endpoint in agent.endpoints:
            endpoints[endpoint] = dict()
            if show_entitys:
                for entity in endpoint.entity:
                    endpoints[endpoint][entity.entity] = []
                    if show_ports:
                        for port in entity.ports:
                            endpoints[endpoint][entity.entity].append(port)
        result_data = dict(agent_id=agent.agent_id, host=agent.host,
                           status=agent.status,
                           ports_range=jsonutils.loads_as_bytes(agent.ports_range),
                           endpoints=endpoints)
        result['data'].append(result_data)
        return result

    def create(self, req, body=None):
        """call by agent in the normal case"""
        body = body or {}
        global_data = get_global()
        try:
            agent = global_data.add_agent(body)
        except (CacheStoneError, AgentHostExist) as e:
            result = resultutils.results(resultcode=manager_common.RESULT_ERROR,
                                         result='Create agent fail,%s:%s' % (e.__class__.__name__, e.message))
            return result
        result = resultutils.results(total=1, pagenum=0, result='Create agent success',
                                     data=[dict(agent_id=agent.agent_id,
                                                host=agent.host,
                                                status=agent.status,
                                                ports_range=agent.ports_range,
                                                endpoints=[endpoint.endpoint for endpoint in agent.endpoints])
                                           ])
        return result

    @BaseContorller.AgentIdformater
    def delete(self, req, agent_id, body=None):
        """call buy agent"""
        # if force is true
        # will not notify agent, just delete agent from database
        body = body or {}
        force = body.get('force', False)
        cache_store = get_cache()
        rpc = get_client()
        global_data = get_global()
        with global_data.delete_agent(agent_id) as agent:
            if not force:
                host_online_key = targetutils.host_online_key(agent.agent_id)
                # make sure agent is online
                agent_ipaddr = cache_store.get(host_online_key)
                if agent_ipaddr is None:
                    raise RpcPrepareError('Can not delete offline agent, try force')
                secret = uuidutils.generate_uuid()
                # tell agent wait delete
                delete_agent_precommit = rpc.call(targetutils.target_agent(agent),
                                                  ctxt={'finishtime': rpcfinishtime()},
                                                  msg={'method': 'delete_agent_precommit',
                                                       'args': {'agent_id': agent.agent_id,
                                                                'agent_type': agent.agent_type,
                                                                'host': agent.host,
                                                                'ipaddr': agent_ipaddr,
                                                                'secret': secret}
                                                       })
                if not delete_agent_precommit:
                    raise RpcResultError('delete_agent_precommit result is None')
                if delete_agent_precommit.get('resultcode') != manager_common.RESULT_SUCCESS:
                    return resultutils.results(result=delete_agent_precommit.get('result'))
        if not force:
            # tell agent delete itself
            LOG.info('Delete agent %s postcommit with secret %s' % (agent_ipaddr, secret))
            rpc.cast(targetutils.target_agent(agent),
                     ctxt={'finishtime': rpcfinishtime()},
                     msg={'method': 'delete_agent_postcommit',
                          'args': {'agent_id': agent.agent_id,
                                   'agent_type': agent.agent_type,
                                   'host': agent.host,
                                   'ipaddr': agent_ipaddr,
                                   'secret': secret}})
        result = resultutils.results(result='Delete agent success',
                                     data=[dict(agent_id=agent.agent_id,
                                                host=agent.host,
                                                status=agent.status,
                                                ports_range=agent.ports_range)
                                           ])
        return result

    @BaseContorller.AgentsIdformater
    def update(self, req, agent_id, body):
        raise NotImplementedError

    def clean(self, req, agent_id):
        session = get_session()
        query = model_query(session, Agent,
                            filter=and_(Agent.agent_id == agent_id,
                                        Agent.status <= manager_common.DELETED))
        entity_query = model_query(session, AgentEntity.entity, filter=Agent.agent_id == agent_id)
        with session.begin():
            entitys = entity_query.all()
            if entitys:
                for entity in entitys:
                    LOG.error('Clean agent fail, entity %s:%d still on %s' %
                              (entity.endpoint, entity.entity, agent_id))
                raise EndpointNotEmpty('Clean agent %s fail, still has %d entitys' % (agent_id, len(entitys)))
            count = query.delete()
            LOG.info('Clean deleted agent %d, agent_id %s' % (count, agent_id))
            return resultutils.results(result='Clean deleted agent success')

    @BaseContorller.AgentIdformater
    def active(self, req, agent_id, body=None):
        """call buy client"""
        body = body or {}
        status = body.get('status', manager_common.ACTIVE)
        if status not in (manager_common.ACTIVE, manager_common.UNACTIVE):
            raise InvalidArgument('Argument status not right')
        cache_store = get_cache()
        rpc = get_client()
        session = get_session()
        query = model_query(session, Agent,
                            filter=and_(Agent.agent_id == agent_id,
                                        Agent.status > manager_common.DELETED))
        agent = query.one()
        host_online_key = targetutils.host_online_key(agent.agent_id)
        # make sure agent is online
        agent_ipaddr = cache_store.get(host_online_key)
        if agent_ipaddr is None:
            raise RpcPrepareError('Can not active or unactive a offline agent: %d' % agent_id)
        with session.begin():
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

    @BaseContorller.AgentIdformater
    def edit(self, req, agent_id, body=None):
        """call by agent"""
        # TODO  check data in body
        body = body or {}
        session = get_session()
        glock = get_global().lock('agents')
        with glock([agent_id, ]) as agents:
            agent = agents[0]
            data = body
            if not data:
                raise InvalidInput('Not data exist')
            with session.begin():
                agent.update(data)
            result = resultutils.results(pagenum=0,
                                         result='Update agent success',
                                         data=[body, ])
            return result

    def online(self, req, body=None):
        """call buy agent
        when a agent start, it will call online to show it's ipaddr
        and get agent_id from gcenter
        """
        body = body or {}
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
        cache_store = get_cache()
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
            exist_host_ipaddr = cache_store.get(host_online_key)
            if exist_host_ipaddr is not None:
                if exist_host_ipaddr != agent_ipaddr:
                    LOG.error('Host call online with %s, but %s alreday exist on redis' %
                              (agent_ipaddr, exist_host_ipaddr))
                    raise InvalidArgument('Host %s with ipaddr %s alreday eixst' % (host, exist_host_ipaddr))
                # key exist, set new expire time
                if not cache_store.expire(host_online_key,
                                            manager_common.ONLINE_EXIST_TIME):
                    if not cache_store.set(host_online_key, agent_ipaddr,
                                           ex=manager_common.ONLINE_EXIST_TIME, nx=True):
                        raise InvalidArgument('Another agent login with same '
                                              'host or someone set key %s' % host_online_key)
            else:
                if not cache_store.set(host_online_key, agent_ipaddr,
                                       ex=manager_common.ONLINE_EXIST_TIME, nx=True):
                    raise InvalidArgument('Another agent login with same host or '
                                          'someone set key %s' % host_online_key)
        result = resultutils.results(result='Online agent function run success')
        result['data'].append(ret)
        return result

    @BaseContorller.AgentIdformater
    def report(self, req, agent_id, body=None):
        body = body or {}
        cache_store = get_cache()
        if body.get('agent_ipaddr'):
            agent_ipaddr = validators['type:ip_address'](body.pop('agent_ipaddr'))
            BaseContorller.agent_ipaddr_cache_flush(cache_store, agent_id, agent_ipaddr)
        pass

    def status(self, req, agent_id, body=None):
        """get status from agent, not from database
        do not need Idsformater, check it in send_asyncrequest
        """
        body = body or {}
        asyncrequest = self.create_asyncrequest(body)
        target = targetutils.target_all(fanout=True)
        rpc_ctxt = {}
        if agent_id != 'all':
            rpc_ctxt.setdefault('agents', self.agents_id_check(agent_id))
        rpc_method = 'status_agent'
        rpc_args = body

        def wapper():
            self.send_asyncrequest(asyncrequest, target,
                                   rpc_ctxt, rpc_method, rpc_args)

        threadpool.add_thread(safe_func_wrapper, wapper, LOG)
        return resultutils.results(result='Status agent async request thread spawning',
                                   data=[asyncrequest.to_dict()])

    @BaseContorller.AgentsIdformater
    def upgrade(self, req, agent_id, body=None):
        """call by client, and asyncrequest
        do not need Idsformater, check it in send_asyncrequest
        send rpm file to upgrade code of agent
        """
        body = body or {}
        asyncrequest = self.create_asyncrequest(body)
        target = targetutils.target_all(fanout=True)
        rpc_method = 'upgrade_agent'
        rpc_args = {'file': body.get('file')}
        rpc_ctxt = {}

        global_data = get_global()
        glock = functools.partial(global_data.lock('agents'), agent_id)

        def wapper():
            with glock() as agents:
                if agents is not manager_common.ALL_AGENTS:
                    agents = [agent.agent_id for agent in agents]
                rpc_ctxt.setdefault('agents', agents)
                self.send_asyncrequest(asyncrequest, target,
                                       rpc_ctxt, rpc_method, rpc_args)

        threadpool.add_thread(safe_func_wrapper, wapper, LOG)
        return resultutils.results(result='Upgrade agent async request thread spawning',
                                   data=[asyncrequest.to_dict()])
