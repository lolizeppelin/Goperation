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

    @BaseContorller.AgentsIdformater
    def index(self, req, agent_id, body):
        session = get_session(readonly=True)
        query = model_query(session, AgentEndpoint, filter=AgentEndpoint.agent_id == agent_id)
        return resultutils.results(result='list endpoint on success',
                                   data=[dict(endpoint=endpoint.endpoint,
                                              entitys=len(endpoint.entitys),
                                              ports=len(endpoint.ports))
                                         for endpoint in query.all()])

    @BaseContorller.AgentsIdformater
    def show(self, req, agent_id, endpoint, body):
        """call buy client"""
        session = get_session(readonly=True)
        endpoints_filter = and_(AgentEndpoint.agent_id == agent_id,
                                AgentEndpoint.endpoint == endpoint)
        query = model_query(session, AgentEndpoint, filter=endpoints_filter)
        return resultutils.results(result='show endpoint success',
                                   data=[dict(endpoint=e.endpoint,
                                              agent_id=e.agent_id,
                                              entitys=[x.entitys for x in endpoint.entitys],
                                              ports=[x.port for x in endpoint.ports]) for e in query.all()])

    @BaseContorller.AgentIdformater
    def create(self, req, agent_id, body):
        endpoints = utils.validate_endpoints(body.get('endpoints'))
        endpoints = utils.validate_endpoints(endpoints)
        session = get_session()
        glock = get_global().lock('agents')
        with glock([agent_id, ]):
            with session.begin(subtransactions=True):
                for endpoint in endpoints:
                    session.add(AgentEndpoint(agent_id=agent_id, endpoint=endpoint))
                    session.flush()
        return resultutils.results(result='add endpoints success')

    @BaseContorller.AgentIdformater
    def delete(self, req, agent_id, endpoint, body):
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

    def synopsis(self, req, endpoint, body):
        endpoint = utils.validate_endpoint(endpoint)
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

    def agents(self, req, endpoint, body):
        session = get_session(readonly=True)
        endpoint = utils.validate_endpoint(endpoint)
        query = model_query(session, Agent,
                            filter=and_(Agent.status > manager_common.DELETED,
                                        endpoint in [endpoint.endpoint for endpoint in Agent.endpoints]))
        return resultutils.results(result='get agent for %s success' % endpoint,
                                   data=[dict(agent_id=agent.agent_id,
                                              agent_host=agent.host,
                                              cpu=agent.cpu,
                                              memory=agent.memory) for agent in query.all()])
