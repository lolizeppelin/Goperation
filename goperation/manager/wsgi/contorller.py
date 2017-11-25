import contextlib

from redis.exceptions import WatchError

from simpleutil.utils import timeutils
from simpleutil.utils import argutils
from simpleutil.utils import uuidutils
from simpleutil.log import log as logging
from simpleutil.common.exceptions import InvalidArgument

from simpleservice.wsgi.middleware import MiddlewareContorller
from simpleservice.ormdb.exceptions import DBDuplicateEntry
from simpleservice.rpc.exceptions import AMQPDestinationNotFound
from simpleservice.rpc.exceptions import MessagingTimeout

from goperation.manager.utils import targetutils
from goperation.manager.utils import common as manager_common
from goperation.manager.api import get_client
from goperation.manager.api import get_session
from goperation.manager.api import get_global
from goperation.manager.api import rpcfinishtime
from goperation.manager.models import AsyncRequest
from goperation.manager.wsgi.exceptions import AsyncRpcPrepareError
from goperation.manager.wsgi.exceptions import RpcResultError


LOG = logging.getLogger(__name__)


@contextlib.contextmanager
def empty_lock():
    yield


class BaseContorller(MiddlewareContorller):

    AgentIdformater = argutils.Idformater(key='agent_id', formatfunc='agent_id_check')
    AgentsIdformater = argutils.Idformater(key='agent_id', formatfunc='agents_id_check')

    query_interval = 0.7
    interval_increase = 0.3

    def agents_id_check(self, agents_id):
        global_data = get_global()
        if agents_id == 'all':
            return global_data.all_agents
        agents_set = argutils.map_to_int(agents_id)
        all_id = global_data.all_agents
        if agents_set != all_id:
            errors = agents_set - all_id
            if (errors):
                raise InvalidArgument('agents id %s can not be found' % str(list(errors)))
        return agents_set

    def agent_id_check(self, agent_id):
        """For one agent"""
        if agent_id == 'all':
            raise InvalidArgument('Just for one agent')
        agent_id = self.agents_id_check(agent_id)
        if len(agent_id) > 1:
            raise InvalidArgument('Just for one agent')
        return agent_id.pop()

    @staticmethod
    def request_id_check(request_id):
        if not uuidutils.is_uuid_like(request_id):
            raise InvalidArgument('Request id is not uuid like')
        return request_id

    @staticmethod
    def create_asyncrequest(body):
        """async request use this to create a new request
        argv in body
        request_time:  unix time in seconds that client send async request
        finishtime:  unix time in seconds that work shoud be finished after this time
        deadline:  unix time in seconds that work will igonre after this time
        expire: respone expire time
        """
        request_time = int(timeutils.realnow())
        expire = body.pop('expire', 0)
        if expire < 0:
            raise InvalidArgument('Async argv expire less thne 0')
        try:
            client_request_time = int(body.pop('request_time'))
        except KeyError:
            raise InvalidArgument('Async request need argument request_time')
        except TypeError:
            raise InvalidArgument('request_time is not int of time or no request_time found')
        offset_time = request_time - client_request_time
        if abs(offset_time) > 5:
            raise InvalidArgument('The offset time between send and receive is %d' % offset_time)
        finishtime = body.pop('finishtime', None)
        if finishtime:
            finishtime = int(finishtime) + offset_time
        else:
            finishtime = rpcfinishtime(request_time)
        if finishtime - request_time < 3:
            raise InvalidArgument('Job can not be finished in 3 second')
        deadline = body.pop('deadline', None)
        if deadline:
            deadline = int(deadline) + offset_time - 1
        else:
            # deadline = rpcdeadline(finishtime)
            deadline = finishtime + 5
        if deadline - finishtime < 3:
            raise InvalidArgument('Job deadline must at least 3 second after finishtime')
        request_id = uuidutils.generate_uuid()
        # req.environ[manager_common.ENV_REQUEST_ID] = request_id
        new_request = AsyncRequest(request_id=request_id,
                                   request_time=request_time,
                                   finishtime=finishtime,
                                   deadline=deadline,
                                   expire=expire)
        return new_request

    @staticmethod
    def agent_ipaddr_cache_flush(cache_store, agent_id, agent_ipaddr):
        host_online_key = targetutils.host_online_key(agent_id)
        with cache_store.pipeline() as pipe:
            pipe.watch(host_online_key)
            pipe.multi()
            pipe.get(host_online_key)
            pipe.ttl(host_online_key)
            pipe.expire(host_online_key, manager_common.ONLINE_EXIST_TIME)
            try:
                results = pipe.execute()
            except WatchError:
                raise InvalidArgument('Host changed')
        exist_agent_ipaddr, ttl, expire_result = results
        if exist_agent_ipaddr is not None:
            if exist_agent_ipaddr != agent_ipaddr:
                LOG.error('Host call online with %s, but %s alreday exist with same key' %
                          (agent_ipaddr, exist_agent_ipaddr))
                if ttl > 2:
                    if not cache_store.expire(host_online_key, ttl):
                        LOG.error('Revet ttl of %s fail' % host_online_key)
                raise InvalidArgument('Agent %d with ipaddr %s alreday eixst' % (agent_id, exist_agent_ipaddr))
        else:
            if not cache_store.set(host_online_key, agent_ipaddr,
                                   ex=manager_common.ONLINE_EXIST_TIME, nx=True):
                raise InvalidArgument('Another agent login with same host or '
                                      'someone set key %s' % host_online_key)

    @staticmethod
    def send_asyncrequest(asyncrequest, rpc_target,
                          rpc_ctxt, rpc_method, rpc_args=None):
        rpc = get_client()
        session = get_session()
        timeout = asyncrequest.finishtime - int(timeutils.realnow()) - 3
        if timeout <= 1:
            raise InvalidArgument('Not enough time for asynrequest')
        timeout = min(timeout, 5)
        try:
            rpc.cast(targetutils.target_rpcserver(),
                     ctxt={'finishtime': asyncrequest.finishtime-2},
                     msg={'method': 'asyncrequest',
                          'args': {'asyncrequest': asyncrequest.to_dict(),
                                   'rpc_target': rpc_target.to_dict(),
                                   'rpc_method': rpc_method,
                                   'rpc_ctxt': rpc_ctxt,
                                   'rpc_args': rpc_args}}, timeout=timeout)
        except (MessagingTimeout, AMQPDestinationNotFound) as e:
            LOG.error('Send async request to scheduler fail %s' % e.__class__.__name__)
            asyncrequest.status = manager_common.FINISH
            asyncrequest.result = e.message
            asyncrequest.resultcode = manager_common.SCHEDULER_NOTIFY_ERROR
            try:
                session.add(asyncrequest)
                session.flush()
            except DBDuplicateEntry:
                LOG.warning('Async request rpc call result is None, but recode found')
        except Exception as e:
            LOG.exception('Async request rpc cast unkonw error')
            asyncrequest.status = manager_common.FINISH
            asyncrequest.result = 'Async request rpc cast error: %s' % e.__class__.__name__
            asyncrequest.resultcode = manager_common.RESULT_ERROR
            try:
                session.add(asyncrequest)
                session.flush()
                raise
            except DBDuplicateEntry:
                LOG.warning('Async request rpc call result is None, but recode found')
