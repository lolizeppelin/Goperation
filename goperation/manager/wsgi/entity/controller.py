import webob.exc

from sqlalchemy.sql import and_
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.orm.exc import MultipleResultsFound

from simpleutil.utils import argutils
from simpleutil.utils.attributes import validators
from simpleutil.log import log as logging
from simpleutil.common.exceptions import InvalidArgument

from simpleservice.ormdb.api import model_query
from simpleservice.ormdb.api import model_autoincrement_id
from simpleservice.rpc.exceptions import AMQPDestinationNotFound
from simpleservice.rpc.exceptions import MessagingTimeout
from simpleservice.rpc.exceptions import NoSuchMethod

from goperation.manager import common as manager_common
from goperation.manager import utils
from goperation.manager import resultutils
from goperation.manager import targetutils

from goperation.manager.api import get_cache
from goperation.manager.api import get_global
from goperation.manager.api import get_session
from goperation.manager.models import AgentEndpoint
from goperation.manager.models import AgentEntity
from goperation.manager.models import AllocatedPort

from goperation.manager.wsgi.contorller import BaseContorller
from goperation.manager.exceptions import CacheStoneError
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
             MultipleResultsFound: webob.exc.HTTPInternalServerError,
             }


class EntityReuest(BaseContorller):

    @BaseContorller.AgentsIdformater
    def index(self, req, endpoint, body):
        agent_id = body.get('agent_id')
        endpoint = utils.validate_endpoint(endpoint)
        session = get_session(readonly=True)
        query = model_query(session, AgentEndpoint, filter=AgentEntity.endpoint == endpoint)
        if agent_id:
            query = query.filter(AgentEntity.agent_id == agent_id)
        endpoint_detail = {}
        for entity in query.all():
            try:
                endpoint_detail[entity.agent_id].append(entity.entity)
            except KeyError:
                endpoint_detail[entity.agent_id] = [entity.entity]
        return resultutils.results(result='show endpoint entitys success',
                                   data=[endpoint_detail, ])

    @BaseContorller.AgentIdformater
    def create(self, req, endpoint, body):
        agent_id = body.pop('agent_id')
        entity_type = body.pop('entity_type')
        endpoint = utils.validate_endpoint(endpoint)
        ports = body.get('ports')
        if ports:
            ports = argutils.map_with(ports, validators['type:port'])
        desc = body.get('desc')
        session = get_session()
        glock = get_global().lock('agents')
        elock = get_global().lock('endpoint')
        with elock(endpoint):
            with glock([agent_id, ]):
                with session.begin(subtransactions=True):
                    entity = AgentEntity(entity=model_autoincrement_id(session, AgentEntity.entity,
                                                                       filter=AgentEntity.endpoint == endpoint),
                                         agent_id=agent_id, endpoint=endpoint,
                                         entity_type=entity_type, desc=desc)
                    if ports:
                        entity.ports = [AllocatedPort(port=port, agent_id=agent_id, endpoint=endpoint)
                                        for port in ports]
                    session.add(entity)
                    session.flush()
        return resultutils.results(result='add entity success', data=[dict(entity=entity, agent_id=agent_id,
                                                                           endpoint=endpoint, entity_type=entity_type,
                                                                           port=ports or [])])

    @BaseContorller.AgentsIdformater
    def show(self, req, endpoint, entity, body):
        session = get_session(readonly=True)
        query = model_query(session, AgentEntity, filter=and_(AgentEntity.endpoint == endpoint,
                                                              AgentEntity.entity == entity))
        return resultutils.results(result='show entity success',
                                   data=[dict(endpoint=e.endpoint,
                                              agent_id=e.agent_id,
                                              entity=e.entity,
                                              ports=[x.port for x in entity.ports]) for e in query.all()])

    @BaseContorller.AgentIdformater
    def delete(self, req, endpoint, entity, body):
        endpoint = utils.validate_endpoint(endpoint)
        entitys = argutils.map_to_int(entity)
        session = get_session()
        glock = get_global().lock('entitys')
        elock = get_global().lock('endpoint')
        with glock(entitys):
            with elock(endpoint):
                with session.begin(subtransactions=True):
                    query = model_query(session, AgentEntity,
                                        filter=and_(AgentEntity.endpoint == endpoint,
                                                    AgentEntity.entity.in_(entitys)))
                    delete_count = query.delete()
                    need_to_delete = len(entitys)
                    if delete_count != len(entitys):
                        LOG.warning('Delete %d entitys, but expect count is %d' % (delete_count, need_to_delete))
        return resultutils.results(result='delete endpoints success')
