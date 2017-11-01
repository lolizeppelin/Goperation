import webob.exc

from sqlalchemy.sql import and_
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.orm.exc import MultipleResultsFound

from simpleutil.log import log as logging
from simpleutil.common.exceptions import InvalidArgument

from simpleservice.ormdb.api import model_query
from simpleservice.ormdb.api import model_count_with_key
from simpleservice.rpc.exceptions import AMQPDestinationNotFound
from simpleservice.rpc.exceptions import MessagingTimeout
from simpleservice.rpc.exceptions import NoSuchMethod

from goperation.manager import common as manager_common
from goperation.manager import utils
from goperation.manager import resultutils
from goperation.manager.api import get_global
from goperation.manager.api import get_session
from goperation.manager.models import AgentEndpoint
from goperation.manager.models import AgentEntity
from goperation.manager.models import AllocatedPort
from goperation.manager.models import Agent

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


class EndpointReuest(BaseContorller):

    @BaseContorller.AgentIdformater
    def index(self, req, agent_id):
        session = get_session(readonly=True)
        query = model_query(session, AgentEndpoint, filter=AgentEndpoint.agent_id == agent_id)
        return resultutils.results(result='list endpoint on success',
                                   data=[dict(endpoint=endpoint.endpoint,
                                              entitys=len(endpoint.entitys),
                                              ports=len(endpoint.ports))
                                         for endpoint in query.all()])

    @BaseContorller.AgentIdformater
    def create(self, req, agent_id, body=None):
        body = body or {}
        endpoints = utils.validate_endpoints(body.get('endpoints'))
        session = get_session()
        glock = get_global().lock('agents')
        with glock([agent_id, ]):
            with session.begin():
                for endpoint in endpoints:
                    session.add(AgentEndpoint(agent_id=agent_id, endpoint=endpoint))
                    session.flush()
            session.commit()
        return resultutils.results(result='add endpoints success',
                                   data=endpoints)

    @BaseContorller.AgentIdformater
    def show(self, req, agent_id, endpoint):
        session = get_session(readonly=True)
        endpoints_filter = and_(AgentEndpoint.agent_id == agent_id,
                                AgentEndpoint.endpoint == endpoint)
        query = model_query(session, AgentEndpoint, filter=endpoints_filter)
        endpoint = query.one()
        return resultutils.results(result='show endpoint success',
                                   data=[dict(endpoint=endpoint.endpoint,
                                              agent_id=endpoint.agent_id,
                                              entitys=[x.entitys for x in endpoint.entitys],
                                              ports=[x.port for x in endpoint.ports])])

    @BaseContorller.AgentIdformater
    def delete(self, req, agent_id, endpoint):
        endpoints = utils.validate_endpoints(endpoint)
        if not endpoints:
            raise InvalidArgument('Endpoints is None for add endpoints')
        endpoints = utils.validate_endpoints(endpoints)
        session = get_session()
        glock = get_global().lock('agents')
        with glock([agent_id, ]):
            with session.begin(subtransactions=True):
                if model_count_with_key(session, AgentEntity.entity,
                                        filter=and_(AgentEntity.agent_id == agent_id,
                                                    AgentEntity.endpoint.in_(endpoints))):
                    return resultutils.results(resultcode=manager_common.RESULT_ERROR,
                                               result='delete endpoints fail, entitys still in endpoint')
                query = model_query(session, AgentEndpoint,
                                    filter=and_(AgentEndpoint.agent_id == agent_id,
                                                AgentEndpoint.endpoint.in_(endpoints)))
                delete_count = query.delete()
                need_to_delete = len(endpoints)
                if delete_count != len(endpoints):
                    LOG.warning('Delete %d endpoints, but expect count is %d' % (delete_count, need_to_delete))
        return resultutils.results(result='delete endpoints success')

    def agents(self, req, endpoint):
        session = get_session(readonly=True)
        endpoint = utils.validate_endpoint(endpoint)
        query = model_query(session, AgentEndpoint, filter=AgentEndpoint.endpoint == endpoint)
        agents = set()
        for endpoint in query.all():
            agents.add(endpoint.agent_id)
        if not agents:
            raise InvalidArgument('No agent found for %s' % endpoint)
        query = model_query(session, Agent,
                            filter=and_(Agent.status > manager_common.DELETED,
                                        Agent.agent_id.in_(agents)))
        return resultutils.results(result='get agent for %s success' % endpoint,
                                   data=[dict(agent_id=agent.agent_id,
                                              agent_host=agent.host,
                                              cpu=agent.cpu,
                                              memory=agent.memory) for agent in query.all()])

    def entitys(self, req, endpoint):
        session = get_session(readonly=True)
        endpoint = utils.validate_endpoint(endpoint)
        query = model_query(session, AgentEntity, filter=AgentEntity.endpoint == endpoint)
        return resultutils.results(result='get endpoint %s entitys success' % endpoint,
                                   data=[dict(agent_id=entity.agent_id,
                                              entity=entity.entity,
                                              entity_type=entity.entity_type,
                                              ports=[port.port for port in entity.ports]) for entity in query.all()])
