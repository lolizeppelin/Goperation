import functools
import webob.exc

from sqlalchemy.sql import and_

from simpleutil.common.exceptions import InvalidArgument
from simpleutil.common.exceptions import InvalidInput
from simpleutil.log import log as logging
from simpleutil.utils import argutils
from simpleutil.utils import timeutils
from simpleutil.utils.attributes import validators

from simpleservice.ormdb.api import model_query
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
             }

class EndpointReuest(BaseContorller):


    @BaseContorller.AgentIdformater
    def show(self, req, agent_id, ports, body):
        """show ports info"""
        session = get_session()
        query = model_query(session, AllocatedPort, filter=AllocatedPort.agent_id == agent_id)
        if ports != 'all':
            query = query.filter(AllocatedPort.port.in_(argutils.map_to_int(ports)))
        return resultutils.results(result='show ports success', data=[dict(port=p.port, endpoint=p.endpoint,
                                                                           entity=p.entity, desc=p.desc,
                                                                           ) for p in query.all()])

    @BaseContorller.AgentIdformater
    def create(self, req, agent_id, endpoint, entity, ports, body):
        if not isinstance(ports, list):
            ports = [ports, ]
        for port in ports:
            if not isinstance(port, (int, long)):
                raise InvalidArgument('Port in ports not int, can not edit ports')
            if not (0 <= port <= 65535):
                raise InvalidArgument('Port in ports over range, can not edit ports')
        session = get_session()
        glock = get_global().lock('agents')
        with glock([agent_id, ]):
            with session.begin(subtransactions=True):
                for port in ports:
                    session.add(AllocatedPort(agent_id=agent_id, port=port, endpoint=endpoint, entity=entity))
                    session.flush()
        return resultutils.results(result='edit ports success')

    @BaseContorller.AgentIdformater
    def delete(self, req, agent_id, endpoint, entity, ports, body):
        ports = argutils.map_to_int(ports)
        strict = body.get('strict', True)
        if not ports:
            raise InvalidArgument('Ports is None for delete ports')
        for port in ports:
            if not isinstance(port, (int, long)):
                raise InvalidArgument('Port in ports not int, can not edit ports')
            if not (0 <= port <= 65535):
                raise InvalidArgument('Port in ports over range, can not edit ports')
        session = get_session()
        glock = get_global().lock('agents')
        with glock([agent_id, ]):
            with session.begin(subtransactions=True):
                query = model_query(session, AllocatedPort, filter=and_(AllocatedPort.agent_id == agent_id,
                                                                        AllocatedPort.endpoint == endpoint,
                                                                        AllocatedPort.entity == entity,
                                                                        AllocatedPort.port.in_(ports)))
                delete_count = query.delete()
                need_to_delete = len(ports)
                if delete_count != len(ports):
                    LOG.warning('Delete %d ports, but expect count is %d' % (delete_count, need_to_delete))
                    if strict:
                        raise InvalidArgument('Submit %d ports, but only %d ports found' %
                                              (len(ports), need_to_delete))

        return resultutils.results(result='edit ports success')



