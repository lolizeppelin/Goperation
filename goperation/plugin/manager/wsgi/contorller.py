import contextlib

from simpleutil.log import log as logging
from simpleutil.utils import timeutils
from simpleutil.utils import uuidutils
from simpleutil.utils import threadgroup
from simpleutil.common.exceptions import InvalidArgument


from simpleservice.ormdb.exceptions import DBDuplicateEntry
from simpleservice.rpc.exceptions import AMQPDestinationNotFound
from simpleservice.rpc.exceptions import MessagingTimeout

from goperation import plugin
from goperation.plugin.utils import safe_fun_wrapper
from goperation.plugin.manager import common as manager_common
from goperation.plugin.manager.wsgi import targetutils
from goperation.plugin.manager.wsgi import resultutils
from goperation.plugin.manager.api import rpcfinishtime
from goperation.plugin.manager.api import get_client
from goperation.plugin.manager.api import get_session
from goperation.plugin.manager.models import AsyncRequest

from goperation.plugin.manager.wsgi.exceptions import RpcResultError
from goperation.plugin.manager.wsgi.exceptions import AsyncRpcPrepareError



LOG = logging.getLogger(__name__)


@contextlib.contextmanager
def empty_lock():
    yield


class BaseContorller():

    query_interval = 0.7
    interval_increase = 0.3

    @staticmethod
    def request_id_check(request_id):
        if not uuidutils.is_uuid_like(request_id):
            raise InvalidArgument('Request id is not uuid like')

    @staticmethod
    def create_asyncrequest(body):
        """async request use this to create a new request
        argv in body
        request_time:  unix time in seconds that client send async request
        finishtime:  unix time in seconds that work shoud be finished after this time
        deadline:  unix time in seconds that work will igonre after this time
        persist: 0 or 1, if zero, respone will store into redis else store into database
        """
        request_time = int(timeutils.realnow())
        persist = body.get('persist', 1)
        if persist not in (0, 1):
            raise InvalidArgument('Async argv persist not in 0, 1')
        try:
            client_request_time = int(body.get('request_time'))
        except KeyError:
            raise InvalidArgument('Async request need argument request_time')
        except TypeError:
            raise InvalidArgument('request_time is not int of time or no request_time found')
        offset_time = request_time - client_request_time
        if abs(offset_time) > 5:
            raise InvalidArgument('The diff time between send and receive is %d' % offset_time)
        finishtime = body.get('finishtime', None)
        if finishtime:
            finishtime = int(finishtime) + offset_time
        else:
            # finishtime = request_time + 4
            finishtime = rpcfinishtime(request_time)
        if finishtime - request_time < 3:
            raise InvalidArgument('Job can not be finished in 3 second')
        deadline = body.get('deadline', None)
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
                                   persist=persist)
        return new_request

    def send_asyncrequest(self, body, target,
                          rpc_method, rpc_ctxt=None, rpc_args=None, lock=None):
        if lock is None:
            lock = empty_lock()
        rpc = get_client()
        session = get_session()
        asyncrequest = self.create_asyncrequest(body)
        rpc_ctxt = rpc_ctxt or {}
        rpc_args = rpc_args or {}
        rpc_args = rpc_args or {}
        try:
            agents = rpc_ctxt.pop('agents')
        except KeyError:
            raise AsyncRpcPrepareError('Not agents found in ctxt')
        def func():
            with lock:
                rpc_ctxt.setdefault('finishtime', asyncrequest.finishtime)
                if callable(agents):
                    _agents = agents()
                else:
                    _agents = agents
                rpc_ctxt.setdefault('agents', list(_agents) if isinstance(_agents, set) else _agents)
                if not isinstance(rpc_ctxt.get('agents'), list):
                    raise AsyncRpcPrepareError('Argument agents in ctxt not list')
                try:
                    async_ret = rpc.call(targetutils.target_anyone(manager_common.SCHEDULER),
                                         ctxt={'finishtime': asyncrequest.finishtime},
                                         msg={'method': 'asyncrequest',
                                              'args': {'asyncrequest': asyncrequest.to_dict(),
                                                       'rpc_target': target.to_dict(),
                                                       'rpc_method': rpc_method,
                                                       'rpc_ctxt': rpc_ctxt,
                                                       'rpc_args': rpc_args}})
                    if not async_ret:
                        raise RpcResultError('Async request rpc call result is None')
                    LOG.debug(async_ret.get('result', 'Async request %s call scheduler result unkonwn'))
                    if async_ret.get('resultcode') == manager_common.RESULT_OVER_FINISHTIME:
                        asyncrequest.status = manager_common.FINISH
                        asyncrequest.resultcode = manager_common.RESULT_OVER_FINISHTIME
                        asyncrequest.result = 'Async request %s call scheduler faile, over finishtime' % rpc_method
                        try:
                            session.add(asyncrequest)
                            session.commit()
                        except DBDuplicateEntry:
                            LOG.warning('Async request rpc call result over finishtime, but recode found')
                except (RpcResultError, MessagingTimeout, AMQPDestinationNotFound) as e:
                    asyncrequest.status = manager_common.FINISH
                    asyncrequest.result = e.message
                    asyncrequest.resultcode = manager_common.RESULT_IS_NONE
                    try:
                        session.add(asyncrequest)
                        session.commit()
                    except DBDuplicateEntry:
                        LOG.warning('Async request rpc call result is None, but recode found')

        plugin.threadpool.add_thread(safe_fun_wrapper, func, LOG)
        return resultutils.results(result=asyncrequest.result, data=[asyncrequest.to_dict()])
