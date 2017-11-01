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
from simpleservice.ormdb.api import model_count_with_key
from simpleservice.rpc.exceptions import AMQPDestinationNotFound
from simpleservice.rpc.exceptions import MessagingTimeout
from simpleservice.rpc.exceptions import NoSuchMethod

from goperation.manager import common as manager_common
from goperation.manager import utils
from goperation.manager import resultutils

from goperation.manager.api import get_global
from goperation.manager.api import get_session
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


class EntityReuest(BaseContorller):

    @BaseContorller.AgentIdformater
    def index(self, req, agent_id, endpoint, body=None):
        body = body or {}
        show_ports = body.get('ports')
        endpoint = utils.validate_endpoint(endpoint)
        session = get_session(readonly=True)
        query = model_query(session, AgentEntity, filter=and_(AgentEntity.endpoint == endpoint,
                                                              AgentEntity.agent_id == agent_id))
        entitys = query.all()
        if not entitys:
            return resultutils.results(result='no entity found', resultcode=manager_common.RESULT_ERROR)
        return resultutils.results(result='show endpoint entitys success',
                                   data=[dict(entity=entity.entity,
                                              entity_type=entity.entity_type,
                                              ports=[port.port for port in entity.ports] if show_ports else [])
                                         for entity in entitys])

    @BaseContorller.AgentIdformater
    def create(self, req, agent_id, endpoint, body=None):
        body = body or {}
        endpoint = utils.validate_endpoint(endpoint)
        entity_type = body.pop('entity_type')
        ports = body.get('ports')
        session = get_session()
        if ports:
            ports = argutils.map_with(ports, validators['type:port'])
            used_ports = model_count_with_key(session, AllocatedPort.port,
                                              filter=and_(AllocatedPort.port.in_(ports),
                                              AllocatedPort.agent_id == agent_id))
            if used_ports:
                raise InvalidArgument('Ports has been used %d' % used_ports)
        desc = body.get('desc')
        glock = get_global().lock('agents')
        elock = get_global().lock('endpoint')
        with elock(endpoint):
            with glock([agent_id, ]):
                with session.begin(subtransactions=True):
                    entity = model_autoincrement_id(session, AgentEntity.entity,
                                                    filter=AgentEntity.endpoint == endpoint)
                    session.add(AgentEntity(entity=entity,
                                            agent_id=agent_id, endpoint=endpoint,
                                            entity_type=entity_type, desc=desc))
                    session.flush()
                    if ports:
                        for port in ports:
                            session.add(AllocatedPort(port=port, agent_id=agent_id,
                                                      endpoint=endpoint, entity=entity))
                            session.flush()
        return resultutils.results(result='add entity success', data=[dict(entity=entity, agent_id=agent_id,
                                                                           endpoint=endpoint, entity_type=entity_type,
                                                                           port=ports or [])])

    def show(self, req, endpoint, entity, body=None):
        body = body or {}
        show_ports = body.get('ports')
        endpoint = utils.validate_endpoint(endpoint)
        entitys = argutils.map_to_int(entity)
        session = get_session(readonly=True)
        query = model_query(session, AgentEntity, filter=and_(AgentEntity.endpoint == endpoint,
                                                              AgentEntity.entity.in_(entitys)))
        entitys = query.all()
        if not entitys:
            return resultutils.results(result='no entity found', resultcode=manager_common.RESULT_ERROR)
        return resultutils.results(result='show entity success',
                                   data=[dict(endpoint=e.endpoint,
                                              agent_id=e.agent_id,
                                              entity=e.entity,
                                              ports=[x.port for x in entity.ports] if show_ports else [])
                                         for e in entitys])

    def delete(self, req, endpoint, entity, body):
        body = body or {}
        strict = body.get('strict')
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
                        if strict:
                            raise DeleteCountNotSame('Need delete %d, but match %d' % (need_to_delete, delete_count))
        return resultutils.results(result='delete endpoints success')
