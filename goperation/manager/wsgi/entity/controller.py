import webob.exc

from sqlalchemy.sql import and_
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.orm.exc import MultipleResultsFound

from simpleutil.utils import argutils
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
    def index(self, req, agent_id, endpoint, body):
        session = get_session(readonly=True)
        query = model_query(session, AgentEntity, filter=and_(AgentEntity.agent_id == agent_id,
                                                              AgentEntity.endpoint == endpoint))
        entitys = query.all()
        return resultutils.results(result='list entity success',
                                   data=[dict(entity=entity.entity,
                                              ports=len(entity.ports)) for entity in entitys])

    @BaseContorller.AgentsIdformater
    def show(self, req, agent_id, endpoint, entity, body):
        session = get_session(readonly=True)
        query = model_query(session, AgentEntity, filter=and_(AgentEntity.agent_id == agent_id,
                                                              AgentEntity.endpoint == endpoint,
                                                              AgentEntity.entity == entity))
        return resultutils.results(result='show entity success',
                                   data=[dict(endpoint=e.endpoint,
                                              agent_id=e.agent_id,
                                              entity=e.entity,
                                              ports=[x.port for x in entity.ports]) for e in query.all()])

    @BaseContorller.AgentIdformater
    def create(self, req, agent_id, endpoint, body):
        endpoint = utils.validate_endpoint(endpoint)
        ports = body.get('ports')
        entity_type = body.get('entity_type')
        desc = body.get('desc')
        session = get_session()
        glock = get_global().lock('agents')
        elock = get_global().lock('endpoint')
        with glock([agent_id, ]):
            with elock(endpoint):
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

    @BaseContorller.AgentIdformater
    def delete(self, req, agent_id, endpoint, entity, body):
        endpoint = utils.validate_endpoint(endpoint)
        entitys = argutils.map_to_int(entity)
        session = get_session()
        glock = get_global().lock('agents')
        elock = get_global().lock('endpoint')
        with glock([agent_id, ]):
            with elock(endpoint):
                with session.begin(subtransactions=True):
                    query = model_query(session, AgentEntity, filter=and_(AgentEntity.agent_id == agent_id,
                                                              AgentEntity.endpoint == endpoint,
                                                              AgentEntity.entity.in_(entitys)))
                    delete_count = query.delete()
                    need_to_delete = len(entitys)
                    if delete_count != len(entitys):
                        LOG.warning('Delete %d entitys, but expect count is %d' % (delete_count, need_to_delete))
        return resultutils.results(result='delete endpoints success')

    def synopsis(self, req, endpoint, entity, body):
        session = get_session(readonly=True)
        query = model_query(session, AgentEndpoint, filter=AgentEndpoint.endpoint == endpoint)
        endpoint_detail = {}
        for endpoint in query.all():
            for entity in endpoint.entitys:
                try:
                    endpoint_detail[endpoint.agent_id].append(entity.entity)
                except KeyError:
                    endpoint_detail[endpoint.agent_id] = [entity.entity]
        return resultutils.results(result='show endpoint success',
                                   data=[endpoint_detail, ])
