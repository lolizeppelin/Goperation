# -*- coding:utf-8 -*-
import eventlet
import random
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

from simpleservice.ormdb.api import model_query
from simpleservice.rpc.exceptions import AMQPDestinationNotFound
from simpleservice.rpc.exceptions import MessagingTimeout
from simpleservice.rpc.exceptions import NoSuchMethod

from goperation import threadpool
from goperation.utils import safe_func_wrapper
from goperation.manager import common as manager_common
from goperation.manager.utils import resultutils
from goperation.manager.utils import targetutils
from goperation.manager.api import get_client
from goperation.manager.api import get_cache
from goperation.manager.api import get_global
from goperation.manager.api import get_session
from goperation.manager.api import rpcfinishtime
from goperation.manager.models import Agent
from goperation.manager.models import AgentEndpoint
from goperation.manager.models import AgentEntity
from goperation.manager.models import AgentReportLog
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

    def allagents(self, req):
        return resultutils.results(result='Get all agent id success',
                                   data=list(get_global().all_agents))

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
                                            option=joinedload(Agent.endpoints, innerjoin=False),
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
            endpoints[endpoint.endpoint] = []
            if show_entitys:
                for entity in endpoint.entitys:
                    _entity = {'entity': entity.entity, 'ports': []}
                    endpoints[endpoint.endpoint].append(_entity)
                    if show_ports:
                        for port in entity.ports:
                           _entity['ports'].append(port['port'])
        result_data = dict(agent_id=agent.agent_id, host=agent.host,
                           status=agent.status,
                           cpu=agent.cpu,
                           memory=agent.memory,
                           disk=agent.disk,
                           ports_range=jsonutils.safe_loads_as_bytes(agent.ports_range) or [],
                           endpoints=endpoints,
                           metadata=BaseContorller.agent_metadata(agent_id),
                           )
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
                                                ports_range=jsonutils.safe_loads_as_bytes(agent.ports_range) or [],
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
        rpc = get_client()
        global_data = get_global()
        metadata = None
        with global_data.delete_agent(agent_id) as agent:
            if not force:
                metadata = BaseContorller.agent_metadata(agent.agent_id)
                if metadata is None:
                    raise RpcPrepareError('Can not delete offline agent, try force')
                agent_ipaddr = metadata.get('local_ip')
                secret = uuidutils.generate_uuid()
                # tell agent wait delete
                delete_agent_precommit = rpc.call(targetutils.target_agent(agent),
                                                  ctxt={'finishtime': rpcfinishtime()},
                                                  msg={'method': 'delete_agent_precommit',
                                                       'args': {'agent_id': agent.agent_id,
                                                                'agent_type': agent.agent_type,
                                                                'host': agent.host,
                                                                'agent_ipaddr': agent_ipaddr,
                                                                'secret': secret}
                                                       })
                if not delete_agent_precommit:
                    raise RpcResultError('delete_agent_precommit result is None')
                if delete_agent_precommit.get('resultcode') != manager_common.RESULT_SUCCESS:
                    return resultutils.results(result=delete_agent_precommit.get('result'),
                                               resultcode=manager_common.RESULT_ERROR)
        # if not force:
                # tell agent delete itself
                LOG.info('Delete agent %s postcommit with secret %s' % (agent_ipaddr, secret))
                rpc.cast(targetutils.target_agent(agent),
                         ctxt={'finishtime': rpcfinishtime()},
                         msg={'method': 'delete_agent_postcommit',
                              'args': {'agent_id': agent.agent_id,
                                       'agent_type': agent.agent_type,
                                       'host': agent.host,
                                       'agent_ipaddr': agent_ipaddr,
                                       'secret': secret}})
        def wapper():
            rpc.cast(targetutils.target_rpcserver(fanout=True),
                     msg={'method': 'deletesource',
                          'args': {'agent_id': agent_id}})
        threadpool.add_thread(safe_func_wrapper, wapper, LOG)
        result = resultutils.results(result='Delete agent success',
                                     data=[dict(agent_id=agent.agent_id,
                                                host=agent.host,
                                                status=agent.status,
                                                metadata=metadata,
                                                ports_range=jsonutils.safe_loads_as_bytes(agent.ports_range) or [])
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
        rpc = get_client()
        session = get_session()
        query = model_query(session, Agent,
                            filter=and_(Agent.agent_id == agent_id,
                                        Agent.status > manager_common.DELETED))
        agent = query.one()
        # make sure agent is online
        metadata = BaseContorller.agent_metadata(agent.agent_id)
        if metadata is None:
            raise RpcPrepareError('Can not active or unactive a offline agent: %d' % agent_id)
        agent_ipaddr = metadata.get('local_ip')
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
                                                    metadata=metadata,
                                                    status=agent.status)
                                               ])
            return result

    @BaseContorller.AgentIdformater
    def edit(self, req, agent_id, body=None):
        """call by agent"""
        # TODO  check data in body
        body = body or {}
        ports_range = body.pop('ports_range', [])
        if ports_range:
            body.setdefault('ports_range', jsonutils.dumps_as_bytes(ports_range))
        session = get_session()
        glock = get_global().lock('agents')
        with glock([agent_id, ]):
            data = body
            if not data:
                raise InvalidInput('Not data exist')
            with session.begin():
                query = model_query(session, Agent, Agent.agent_id == agent_id)
                query.update(data)
            result = resultutils.results(pagenum=0,
                                         result='Update agent success',
                                         data=[body, ])
            return result

    @BaseContorller.AgentIdformater
    def report(self, req, agent_id, body=None):
        body = body or {}
        # agent元数据
        metadata = body.pop('metadata')
        # 元数据缓存时间
        expire = body.pop('expire')
        # 性能快照
        snapshot = body.get('snapshot')
        # 随机延迟最长时间是15秒,所以expire时间增加15秒
        if metadata:
            # 有元数据传入,更新缓存中元数据
            eventlet.spawn_n(BaseContorller.agent_metadata_flush, agent_id, metadata, expire+15)
        else:
            # 没有元数据,延长缓存中的元数据持续时间
            # 随机延迟3-15秒,避免所有agent在同一时间更新metadata
            delay = random.randint(0, min(15, expire/10))
            eventlet.spawn_after(delay, BaseContorller.agent_metadata_expire(agent_id, expire+15))
        if snapshot:
            snapshot.setdefault('agent_id', agent_id)
            def wapper():
                eventlet.sleep(random.randint(0, 5))
                # save report log
                session = get_session()
                report = AgentReportLog(**snapshot)
                session.add(report)
                session.flush()
                session.close()
                process = snapshot.get('running') + snapshot.get('sleeping')
                free = snapshot.get('free') + snapshot.get('cached')
                conns = snapshot.get('syn') + snapshot.get('enable')
                cputime = snapshot.get('iowait') + snapshot.get('user') \
                          + snapshot.get('system') + snapshot.get('nice')\
                          + snapshot.get('irq') + snapshot.get('sirq')
                rpc = get_client()
                # send to rpc server
                rpc.cast(targetutils.target_rpcserver(fanout=True),
                         ctxt = {},
                         msg={'method': 'changesource',
                              'args': {'agent_id': agent_id,
                                       'free':  free,
                                       'process': process,
                                       'cputime': cputime,
                                       'iowait': snapshot.get('iowait'),
                                       'left': snapshot.get('left'),
                                       'fds': snapshot.get('num_fds'),
                                       'conns': conns,
                                       'metadata': metadata,
                                       }})
            threadpool.add_thread(safe_func_wrapper, wapper, LOG)
        return resultutils.results(result='report success')

    def status(self, req, agent_id, body=None):
        """get status from agent, not from database
        do not need Idsformater, check it in send_asyncrequest
        """
        body = body or {}
        body.setdefault('expire', 180)
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
        glock = global_data.lock('agents')

        def wapper():
            with glock([agent_id, ]):
                rpc_ctxt.setdefault('agents', [agent_id, ])
                self.send_asyncrequest(asyncrequest, target,
                                       rpc_ctxt, rpc_method, rpc_args)

        threadpool.add_thread(safe_func_wrapper, wapper, LOG)
        return resultutils.results(result='Upgrade agent async request thread spawning',
                                   data=[asyncrequest.to_dict()])
