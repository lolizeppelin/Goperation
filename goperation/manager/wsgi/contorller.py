import contextlib

from simpleutil.utils import timeutils
from simpleutil.utils import argutils
from simpleutil.utils import uuidutils
from simpleutil.log import log as logging
from simpleutil.common.exceptions import InvalidArgument

from simpleservice.ormdb.exceptions import DBDuplicateEntry
from simpleservice.rpc.exceptions import AMQPDestinationNotFound
from simpleservice.rpc.exceptions import MessagingTimeout

from goperation import threadpool
from goperation.utils import safe_fun_wrapper
from goperation.manager import resultutils
from goperation.manager import targetutils
from goperation.manager import common as manager_common
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


class BaseContorller(object):

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

    def send_asyncrequest(self, target, asyncrequest,
                          rpc_method, rpc_ctxt=None, rpc_args=None,
                          lock=None):
        if lock is None:
            lock = empty_lock
        rpc = get_client()
        session = get_session()
        rpc_ctxt = rpc_ctxt or {}
        rpc_args = rpc_args or {}
        rpc_args = rpc_args or {}
        def func():
            with lock() as lock_objs:
                rpc_ctxt.setdefault('finishtime', asyncrequest.finishtime)
                if lock_objs is manager_common.ALL_AGENTS:
                    pass
                    # agents = [  agent.agent_id for agent in  ]

                rpc_ctxt.setdefault('agents', )
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
                            session.flush()
                        except DBDuplicateEntry:
                            LOG.warning('Async request rpc call result over finishtime, but recode found')
                except (RpcResultError, MessagingTimeout, AMQPDestinationNotFound) as e:
                    asyncrequest.status = manager_common.FINISH
                    asyncrequest.result = e.message
                    asyncrequest.resultcode = manager_common.RESULT_IS_NONE
                    try:
                        session.add(asyncrequest)
                        session.flush()
                    except DBDuplicateEntry:
                        LOG.warning('Async request rpc call result is None, but recode found')

        threadpool.add_thread(safe_fun_wrapper, func, LOG)
        return resultutils.results(result=asyncrequest.result, data=[asyncrequest.to_dict()])
