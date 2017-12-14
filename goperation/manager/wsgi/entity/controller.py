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
from goperation.manager.api import get_cache
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
        ports = body.get('ports')
        notify = body.get('notify', True)
        desc = body.get('desc')
        session = get_session()
        if ports:
            ports = argutils.map_with(ports, validators['type:port'])
            used_ports = model_count_with_key(session, AllocatedPort.port,
                                              filter=and_(AllocatedPort.port.in_(ports),
                                                          AllocatedPort.agent_id == agent_id))
            if used_ports:
                raise InvalidArgument('Ports has been used count %d' % used_ports)

        if notify:
            cache_store = get_cache()
            host_online_key = targetutils.host_online_key(agent_id)
            # make sure agent is online
            if not cache_store.get(host_online_key):
                raise RpcPrepareError('Can not create entity on a offline agent %d' % agent_id)

        entity = 0
        glock = get_global().lock('agents')
        elock = get_global().lock('endpoint')
        result = 'add entity success.'
        with glock([agent_id, ]):
            with elock(endpoint):
                with session.begin(subtransactions=True):
                    agent = model_query(session, Agent, filter=Agent.agent_id == agent_id).one()
                    if agent.status != manager_common.ACTIVE:
                        raise InvalidArgument('Create entity fail, agent status is not active,')
                    entity = model_autoincrement_id(session, AgentEntity.entity,
                                                    filter=AgentEntity.endpoint == endpoint)
                    session.add(AgentEntity(entity=entity,
                                            agent_id=agent_id, endpoint=endpoint, desc=desc))
                    session.flush()
                    if ports:
                        for port in ports:
                            session.add(AllocatedPort(port=port, agent_id=agent_id,
                                                      endpoint=endpoint, entity=entity))
                            session.flush()
                    if notify:
                        target = targetutils.target_agent(agent)
                        target.namespace = endpoint
                        body.setdefault('entity', entity)
                        result += self.notify_create(target, entity, body)
        return resultutils.results(result=result, data=[dict(entity=entity, agent_id=agent_id,
                                                             endpoint=endpoint, port=ports or [])])

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
        entitys = query.all()
        if not entitys:
            raise InvalidArgument('no entity found')
            # return resultutils.results(result='no entity found', resultcode=manager_common.RESULT_ERROR)
        return resultutils.results(result='show entity success',
                                   data=[dict(endpoint=e.endpoint,
                                              agent_id=e.agent_id,
                                              entity=e.entity,
                                              ports=[x.port for x in e.ports] if show_ports else [])
                                         for e in entitys])

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
                    attributes = BaseContorller.agent_attributes(agent_id)
                    if not attributes:
                        raise InvalidArgument('Agent not online or not exist')
                delete_count = query.delete()
                if not delete_count:
                    LOG.warning('Delete no entitys, but expect count 1')
                if not force:
                    target = targetutils.target_agent_by_string(attributes.get('agent_type'),
                                                                attributes.get('host'))
                    target.namespace = endpoint
                    body.setdefault('entity', entity)
                    result += self.notify_delete(target, entity, body)
        return resultutils.results(result=result)

    @staticmethod
    def notify_create(target, entity, body):
        rpc = get_client()
        body.setdefault('entity', entity)
        create_ret = rpc.call(target, ctxt={'finishtime': body.pop('finishtime', rpcfinishtime()),
                                            'entitys': [entity, ]},
                              msg={'method': 'create_entity', 'args': body})
        if not create_ret:
            raise RpcResultError('create entitys result is None')
        if create_ret.get('resultcode') != manager_common.RESULT_SUCCESS:
            raise RpcResultError('create entitys fail %s' % create_ret.get('result'))
        return create_ret.get('result')

    @staticmethod
    def notify_delete(target, entity, body):
        rpc = get_client()
        body.setdefault('entity', entity)
        delete_ret = rpc.call(target, ctxt={'finishtime': body.pop('finishtime', rpcfinishtime()),
                                            'entitys': [entity, ]},
                              msg={'method': 'delete_entity', 'args': body})
        if not delete_ret:
            raise RpcResultError('delete entity result is None')
        if delete_ret.get('resultcode') != manager_common.RESULT_SUCCESS:
            raise RpcResultError('delete entity fail %s' % delete_ret.get('result'))
        return delete_ret.get('result')
