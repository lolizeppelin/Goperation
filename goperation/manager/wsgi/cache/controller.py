import time
import string
import random
import webob.exc

from sqlalchemy.sql import and_
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.orm.exc import MultipleResultsFound

from simpleutil.utils import singleton
from simpleutil.utils import jsonutils
from simpleutil.common.exceptions import InvalidArgument
from simpleutil.common.exceptions import InvalidInput
from simpleutil.config import cfg
from simpleutil.log import log as logging
from simpleutil.utils.attributes import validators

from simpleservice.ormdb.api import model_query
from simpleservice.rpc.exceptions import AMQPDestinationNotFound
from simpleservice.rpc.exceptions import MessagingTimeout
from simpleservice.rpc.exceptions import NoSuchMethod

from goperation.manager import common as manager_common
from goperation.manager.config import manager_group
from goperation.manager.utils import resultutils
from goperation.manager.api import get_global
from goperation.manager.api import get_session
from goperation.manager.api import get_cache
from goperation.manager.models import Agent
from goperation.manager.exceptions import CacheStoneError
from goperation.manager.wsgi.contorller import BaseContorller
from goperation.manager.wsgi.exceptions import RpcPrepareError
from goperation.manager.wsgi.exceptions import RpcResultError


LOG = logging.getLogger(__name__)

CONF = cfg.CONF

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
class CacheReuest(BaseContorller):
    PREFIX = CONF[manager_group.name].redis_key_prefix

    def create(self, req, body=None):
        expire = int(body.get('expire') or 30)
        cache = get_cache()
        salt = ''.join(random.sample(string.lowercase, 6))
        key = '-'.join([self.PREFIX, 'caches', str(int(time.time())), salt])
        if not cache.set(key, jsonutils.dumps_as_bytes(body) if body else '',
                         ex=expire or manager_common.ONLINE_EXIST_TIME, nx=True):
            raise CacheStoneError('Cache key value error')
        return resultutils.results(result='Make cache success', data=[key])

    def show(self, req, key, body=None):
        if not key.startswith('-'.join([self.PREFIX, 'caches'])):
            raise InvalidArgument('Key prefix not match')
        if '*' in key:
            raise InvalidArgument('* in key!')
        cache = get_cache()
        data = cache.get(key)
        if data is None:
            return resultutils.results(result='Get cache fail, key not exist or expired',
                                       resultcode=manager_common.RESULT_ERROR)
        if data:
            data = jsonutils.loads_as_bytes(data)
        return resultutils.results(result='Delete cache success', data=[data, ])

    def delete(self, req, key, body=None):
        if not key.startswith('-'.join([self.PREFIX, 'caches'])):
            raise InvalidArgument('Key prefix not match')
        if '*' in key:
            raise InvalidArgument('* in key!')
        cache = get_cache()
        cache.delete(key)
        return resultutils.results(result='Delete cache success', data=[key])

    def update(self, req, key, body=None):
        raise NotImplementedError('Cache can not be update')

    def flush(self, req, body=None):
        """flush cached key"""
        global_data = get_global()
        global_data.flush_all_agents()
        if body.get('online', False):
            global_data.flush_onlines()
        return resultutils.results(result='Flush agents cache id success')

    def online(self, req, host, body):
        """call buy agent
        when a agent start, it will cache agent ipaddr
        """
        try:
            host = validators['type:hostname'](host)
            agent_type = body.pop('agent_type')
            metadata = body.pop('metadata')
            expire = body.pop('expire')
        except KeyError as e:
            raise InvalidArgument('Can not find argument: %s' % e.message)
        except ValueError as e:
            raise InvalidArgument('Argument value type error: %s' % e.message)
        except InvalidInput as e:
            raise InvalidArgument(e.message)
        session = get_session(readonly=True)
        query = model_query(session, Agent,
                            filter=(and_(Agent.status > manager_common.DELETED,
                                         Agent.agent_type == agent_type, Agent.host == host)))
        agent = query.one_or_none()
        if not agent:
            LOG.info('Cache online called but no Agent found')
            ret = {'agent_id': None}
        else:
            self.agent_id_check(agent.agent_id)
            local_ip = metadata.get('local_ip')
            external_ips = str(metadata.get('external_ips'))
            LOG.debug('Cache online called. agent_id:%(agent_id)s, type:%(agent_type)s, '
                      'host:%(host)s, local_ip:%(local_ip)s, external_ips:%(external_ips)s' %
                      {'agent_id': agent.agent_id,
                       'agent_type': agent_type,
                       'host': host,
                       'local_ip': local_ip,
                       'external_ips': external_ips})
            ret = {'agent_id': agent.agent_id}
            BaseContorller._agent_metadata_flush(agent.agent_id, metadata, expire=expire)
        result = resultutils.results(result='Cache online function run success')
        result['data'].append(ret)
        return result
