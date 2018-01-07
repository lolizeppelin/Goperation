import time
import webob.exc

from sqlalchemy.sql import and_
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.orm.exc import MultipleResultsFound

from simpleutil.utils import argutils
from simpleutil.utils import singleton
from simpleutil.utils.attributes import validators
from simpleutil.log import log as logging
from simpleutil.common.exceptions import InvalidArgument

from simpleservice.ormdb.api import model_query
from simpleservice.ormdb.api import model_autoincrement_id
from simpleservice.ormdb.api import model_count_with_key
from simpleservice.rpc.exceptions import AMQPDestinationNotFound
from simpleservice.rpc.exceptions import MessagingTimeout
from simpleservice.rpc.exceptions import NoSuchMethod

from goperation.manager import common as manager_common
from goperation.manager.utils import validateutils
from goperation.manager.utils import resultutils
from goperation.manager.utils import targetutils

from goperation.manager.api import get_global
from goperation.manager.api import get_session
from goperation.manager.api import get_client
from goperation.manager.api import rpcfinishtime
from goperation.manager.models import Agent
from goperation.manager.models import AgentEntity
from goperation.manager.models import AllocatedPort

from goperation.manager.wsgi.contorller import BaseContorller
from goperation.manager.exceptions import CacheStoneError
from goperation.manager.exceptions import DeleteCountNotSame
from goperation.manager.wsgi.exceptions import RpcPrepareError
from goperation.manager.wsgi.exceptions import RpcResultError


LOG = logging.getLogger(__name__)

FAULT_MAP = {InvalidArgument: webob.exc.HTTPClientError,
             NoSuchMethod: webob.exc.HTTPNotImplemented,
             AMQPDestinationNotFound: webob.exc.HTTPServiceUnavailable,
             MessagingTimeout: webob.exc.HTTPServiceUnavailable,
             RpcResultError: webob.exc.HTTPInternalServerError,
             DeleteCountNotSame: webob.exc.HTTPInternalServerError,
             CacheStoneError: webob.exc.HTTPInternalServerError,
             RpcPrepareError: webob.exc.HTTPInternalServerError,
             NoResultFound: webob.exc.HTTPNotFound,
             MultipleResultsFound: webob.exc.HTTPInternalServerError,
             }


@singleton.singleton
class EntityReuest(BaseContorller):

    @BaseContorller.AgentIdformater
    def index(self, req, agent_id, endpoint, body=None):
        body = body or {}
        show_ports = body.get('ports')
        endpoint = validateutils.validate_endpoint(endpoint)
        session = get_session(readonly=True)
        query = model_query(session, AgentEntity, filter=and_(AgentEntity.endpoint == endpoint,
                                                              AgentEntity.agent_id == agent_id))
        if show_ports:
            query = query.options(joinedload(AgentEntity.ports, innerjoin=False))
        entitys = query.all()
        return resultutils.results(result='show endpoint entitys success',
                                   data=[dict(entity=entity.entity,
                                              ports=[port.port for port in entity.ports] if show_ports else [])
                                         for entity in entitys])

    def create(self, req, agent_id, endpoint, body=None):
        body = body or {}
        endpoint = validateutils.validate_endpoint(endpoint)
        ports = body.pop('ports', None)
        notify = body.pop('notify', True)
        desc = body.pop('desc', None)
        session = get_session()
        metadata = None
        if ports:
            ports = argutils.map_with(ports, validators['type:port'])
            used_ports = model_count_with_key(session, AllocatedPort.port,
                                              filter=and_(AllocatedPort.agent_id == agent_id,
                                                          AllocatedPort.port.in_(ports)))
            if used_ports:
                raise InvalidArgument('Ports has been used count %d' % used_ports)

        if notify:
            metadata = BaseContorller.agent_metadata(agent_id)
            # make sure agent is online
            if not metadata:
                raise RpcPrepareError('Can not create entity on a offline agent %d' % agent_id)

        entity = 0
        glock = get_global().lock('agents')
        elock = get_global().lock('endpoint')
        result = 'add entity success.'
        with glock([agent_id, ]):
            with elock(endpoint):
                with session.begin(subtransactions=True):
                    query = model_query(session, Agent, filter=Agent.agent_id == agent_id)
                    query = query.options(joinedload(Agent.endpoints, innerjoin=False))
                    agent = query.one()
                    if agent.status != manager_common.ACTIVE:
                        raise InvalidArgument('Create entity fail, agent status is not active')

                    _endpoint = None
                    for e in agent.endpoints:
                        if endpoint == e.endpoint:
                            _endpoint = e
                            break
                    if not _endpoint:
                        raise InvalidArgument('Create entity fail, agent %d has no endpoint %s' % (agent_id,
                                                                                                   endpoint))
                    entity = model_autoincrement_id(session, AgentEntity.entity,
                                                    filter=AgentEntity.endpoint == endpoint)
                    _entity = AgentEntity(entity=entity, endpoint=endpoint,
                                          agent_id=agent_id, endpoint_id=_endpoint.id, desc=desc)
                    session.add(_entity)
                    session.flush()
                    LOG.info('Create entity with id %s' % str(_entity.id))
                    if ports:
                        for port in ports:
                            session.add(AllocatedPort(port=port, agent_id=agent_id,
                                                      endpoint_id=_endpoint.id,
                                                      entity_id=entity.id,
                                                      endpoint=endpoint, entity=entity))
                            session.flush()
                    if notify:
                        target = targetutils.target_agent(agent)
                        target.namespace = endpoint
                        result += self.notify_create(target, agent.agent_id, entity, body)
        return resultutils.results(result=result, data=[dict(entity=entity, agent_id=agent_id,
                                                             metadata=metadata,
                                                             endpoint=endpoint, port=ports or [])])

    def post_create_entity(self, entity, endpoint, **kwargs):
        entity = int(entity)
        endpoint = validateutils.validate_endpoint(endpoint)
        session = get_session(readonly=True)
        query = model_query(session, AgentEntity, filter=and_(AgentEntity.endpoint == endpoint,
                                                              AgentEntity.entity == entity))
        _entity = query.one()
        metadata = BaseContorller.agent_metadata(_entity.agent_id)
        if not metadata:
            raise RpcPrepareError('Agent not online, can not sen post create')
        target = targetutils.target_agent_by_string(metadata.get('agent_type'),
                                                    metadata.get('host'),)
        target.namespace = endpoint
        body = dict(entity=entity)
        body.update(kwargs)
        rpc = get_client()
        rpc.cast(target, ctxt={'finishtime': body.pop('finishtime', rpcfinishtime()[0]), 'entitys': [entity, ]},
                 msg={'method': 'post_create_entity', 'args': body})
        return resultutils.results(result='notify post create success',
                                   data=[dict(entity=entity, agent_id=_entity.agent_id,
                                              endpoint=endpoint)])

    def show(self, req, endpoint, entity, body=None):
        body = body or {}
        show_ports = body.get('ports', False)
        endpoint = validateutils.validate_endpoint(endpoint)
        entity = int(entity)
        session = get_session(readonly=True)
        query = model_query(session, AgentEntity, filter=and_(AgentEntity.endpoint == endpoint,
                                                              AgentEntity.entity == entity))
        if show_ports:
            query = query.options(joinedload(AgentEntity.ports, innerjoin=False))
        _entity = query.one_or_none()
        if not _entity:
            raise InvalidArgument('no entity found for %s' % endpoint)
            # return resultutils.results(result='no entity found', resultcode=manager_common.RESULT_ERROR)
        return resultutils.results(result='show entity success',
                                   data=[dict(endpoint=_entity.endpoint,
                                              agent_id=_entity.agent_id,
                                              metadata=BaseContorller.agent_metadata(_entity.agent_id),
                                              entity=_entity.entity,
                                              ports=sorted([x.port for x in _entity.ports]) if show_ports else [])])

    def delete(self, req, endpoint, entity, body=None):
        body = body or {}
        force = body.pop('force', False)
        endpoint = validateutils.validate_endpoint(endpoint)
        entity = int(entity)
        session = get_session()
        glock = get_global().lock('entitys')
        result = 'delete entity success.'
        with glock(endpoint, [entity, ]) as agents:
            with session.begin():
                query = model_query(session, AgentEntity,
                                    filter=and_(AgentEntity.endpoint == endpoint,
                                                AgentEntity.entity == entity))
                if not force:
                    agent_id = agents.pop()
                    metadata = BaseContorller.agent_metadata(agent_id)
                    if not metadata:
                        raise InvalidArgument('Agent not online or not exist')
                _entity = query.one_or_none()

                if not _entity:
                    LOG.warning('Delete no entitys, but expect count 1')
                else:
                    query.delete()
                    # pquery = model_query(session, AllocatedPort, filter=AllocatedPort._entity == _entity.id)
                    # pquery.delete()
                if not force:
                    target = targetutils.target_agent_by_string(metadata.get('agent_type'),
                                                                metadata.get('host'))
                    target.namespace = endpoint
                    result += self.notify_delete(target, agent_id, entity, body)
        return resultutils.results(result=result)

    @staticmethod
    def notify_create(target, agent_id, entity, body):
        rpc = get_client()
        body.setdefault('entity', entity)
        finishtime = body.pop('finishtime', None)
        if finishtime is None:
            finishtime, timeout = rpcfinishtime()
        else:
            timeout = finishtime - int(time.time()) + 1
        if timeout < 3:
            raise InvalidArgument('Timeout less then 3')
        create_ret = rpc.call(target, ctxt={'finishtime': finishtime,
                                            'agents': [agent_id, ], 'entitys': [entity, ]},
                              msg={'method': 'create_entity', 'args': body},
                              timeout=timeout)
        if not create_ret:
            raise RpcResultError('create entitys result is None')
        if create_ret.get('resultcode') != manager_common.RESULT_SUCCESS:
            raise RpcResultError('create entity fail %s' % create_ret.get('result'))
        return create_ret.get('result')

    @staticmethod
    def notify_delete(target, agent_id, entity, body):
        rpc = get_client()
        body.setdefault('entity', entity)
        token = body.get('token')
        finishtime = body.pop('finishtime', None)
        if finishtime is None:
            finishtime, timeout = rpcfinishtime()
        else:
            timeout = finishtime - int(time.time()) + 1
        if timeout < 3:
            raise InvalidArgument('Timeout less then 3')
        if token:
            # send a delete token
            rpc.cast(target, ctxt={'finishtime': finishtime,
                                   'entitys': [entity, ]},
                     msg={'method': 'entity_token', 'args': {'entity': entity, 'token': token}})
        delete_ret = rpc.call(target, ctxt={'finishtime': finishtime,
                                            'agents': [agent_id, ], 'entitys': [entity, ]},
                              msg={'method': 'delete_entity', 'args': body},
                              timeout=timeout)
        if not delete_ret:
            raise RpcResultError('delete entity result is None')
        if delete_ret.get('resultcode') != manager_common.RESULT_SUCCESS:
            raise RpcResultError('delete entity fail %s' % delete_ret.get('result'))
        return delete_ret.get('result')

    @staticmethod
    def shows(endpoint, entitys=None, agents=None,
              ports=True, metadata=True):
        endpoint = validateutils.validate_endpoint(endpoint)
        session = get_session(readonly=True)
        filters = [AgentEntity.endpoint == endpoint]
        if entitys:
            entitys = argutils.map_to_int(entitys)
            filters.append(AgentEntity.entity.in_(entitys))
        if agents:
            agents = argutils.map_to_int(agents)
            filters.append(AgentEntity.agent_id.in_(agents))
        if len(filters) > 1:
            filter = and_(*filters)
        else:
            filter = filters[0]
        query = model_query(session, AgentEntity, filter=filter)
        if ports:
            query = query.options(joinedload(AgentEntity.ports, innerjoin=False))
        agents = set()
        entitys_map = {}
        for _entity in query:
            agents.add(_entity.agent_id)
            entitys_map[_entity.entity] = dict(agent_id=_entity.agent_id)
            if ports:
                entitys_map[_entity.entity].setdefault('ports', sorted([x.port for x in _entity.ports]))
        if metadata:
            agents_map = BaseContorller.agents_metadata(agents)

        for _entity in entitys_map:
            agent_id = entitys_map[_entity].get('agent_id')
            if metadata:
                entitys_map[_entity].setdefault('metadata', agents_map[agent_id])

        return entitys_map