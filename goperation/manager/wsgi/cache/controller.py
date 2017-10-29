import webob.exc

from sqlalchemy.sql import and_
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.orm.exc import MultipleResultsFound

from simpleutil.common.exceptions import InvalidArgument
from simpleutil.common.exceptions import InvalidInput
from simpleutil.log import log as logging
from simpleutil.utils.attributes import validators

from simpleservice.ormdb.api import model_query
from simpleservice.rpc.exceptions import AMQPDestinationNotFound
from simpleservice.rpc.exceptions import MessagingTimeout
from simpleservice.rpc.exceptions import NoSuchMethod

from goperation.manager import common as manager_common
from goperation.manager import resultutils
from goperation.manager import targetutils
from goperation.manager.api import get_cache
from goperation.manager.api import get_global
from goperation.manager.api import get_session
from goperation.manager.models import Agent
from goperation.manager.exceptions import CacheStoneError
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


class CacheReuest(BaseContorller):

    def flush(self, req, host, body=None):
        """flush redis key storage"""
        cache_store = get_cache()
        get_global().flush_all_agents()
        if body.get('online', False):
            glock = get_global().lock('all_agents')
            with glock():
                # clean host online key
                keys = cache_store.keys(targetutils.host_online_key('*'))
                if keys:
                    with cache_store.pipeline() as pipe:
                        pipe.multi()
                        for key in keys:
                            pipe.delete(key)
                        pipe.execute()
        return resultutils.results(result='Delete cache id success')

    def online(self, req, host, body):
        """call buy agent
        when a agent start, it will call online to show it's ipaddr
        and get agent_id from gcenter
        """
        try:
            host = validators['type:hostname'](host)
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
            ret = {'agent_id': agent.agent_id}
            host_online_key = targetutils.host_online_key(agent.agent_id)
            exist_host_ipaddr = cache_store.get(host_online_key)
            if exist_host_ipaddr is not None:
                if exist_host_ipaddr != agent_ipaddr:
                    LOG.error('Host call online with %s, but %s alreday exist on redis' %
                              (agent_ipaddr, exist_host_ipaddr))
                    raise InvalidArgument('Host %s with ipaddr %s alreday eixst' % (host, exist_host_ipaddr))
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
