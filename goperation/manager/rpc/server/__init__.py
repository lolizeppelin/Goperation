import time
import eventlet


from simpleutil.config import cfg
from simpleutil.log import log as logging
from simpleutil.utils.timeutils import realnow

from simpleservice.rpc.target import Target
from simpleservice.rpc.exceptions import AMQPDestinationNotFound
from simpleservice.ormdb.exceptions import DBDuplicateEntry
from simpleservice.ormdb.exceptions import DBError
from simpleservice.ormdb.api import model_query

from goperation import threadpool
from goperation.utils import safe_func_wrapper
from goperation.manager import common as manager_common
from goperation.manager.api import get_client
from goperation.manager.api import get_session
from goperation.manager.api import get_cache
from goperation.manager.models import AsyncRequest
from goperation.manager.models import Agent
from goperation.manager.utils import targetutils
from goperation.manager.utils import responeutils

from goperation.manager.rpc.base import RpcManagerBase


LOG = logging.getLogger(__name__)

CONF = cfg.CONF


class RpcServerManager(RpcManagerBase):

    def __init__(self):
        # init httpclient
        super(RpcServerManager, self).__init__(target=targetutils.target_rpcserver(CONF.host))

    def pre_start(self, external_objects):
        super(RpcServerManager, self).pre_start(external_objects)
        # get agent id of this agent
        # if agent not exist,call create
        # add online report periodic tasks
        # self._periodic_tasks.insert(0, OnlinTaskReporter(self))

    def post_start(self):
        self.force_status(manager_common.ACTIVE)

    def full(self):
        if not self.is_active:
            return True
        with self.work_lock.priority(0):
            if self.status != manager_common.ACTIVE:
                return True
            if threadpool.pool.free() < 5:
                return True
        return False

    def rpc_asyncrequest(self, ctxt,
                         asyncrequest, rpc_target, rpc_method,
                         rpc_ctxt, rpc_args):
        session = get_session()
        finishtime = ctxt.get('finishtime', None)
        asyncrequest = AsyncRequest(**asyncrequest)

        if finishtime and int(realnow()) >= finishtime:
            asyncrequest.resultcode = manager_common.RESULT_OVER_FINISHTIME
            asyncrequest.result = 'Async request over finish time'
            asyncrequest.status = manager_common.FINISH
            try:
                session.add(asyncrequest)
                session.flush()
            except DBDuplicateEntry:
                LOG.warning('Async request record DBDuplicateEntry')
            except DBError as e:
                LOG.error('Async request record DBError %s: %s' % (e.__class__.__name__, e.message))
            return

        if not self.is_active:
            asyncrequest.resultcode = manager_common.SCHEDULER_STATUS_ERROR
            asyncrequest.result = 'Scheduler not active now'
            asyncrequest.status = manager_common.FINISH
            session.add(asyncrequest)
            session.flush()
            return

        if rpc_ctxt.get('agents') is None:
            wait_agents = [x[0] for x in model_query(session, Agent.agent_id,
                                                     filter=Agent.status > manager_common.DELETED).all()]
        else:
            wait_agents = rpc_ctxt.get('agents')
        rpc_ctxt.setdefault('request_id', asyncrequest.request_id)
        rpc_ctxt.setdefault('expire', asyncrequest.expire)

        target = Target(**rpc_target)
        rpc = get_client()
        try:
            rpc.cast(target, ctxt=rpc_ctxt, msg={'method': rpc_method, 'args': rpc_args})
        except AMQPDestinationNotFound:
            asyncrequest.resultcode = manager_common.SEND_FAIL
            asyncrequest.result = 'Async %s request send fail, AMQPDestinationNotFound' % rpc_method
            asyncrequest.status = manager_common.FINISH
            session.add(asyncrequest)
            session.flush()
            return

        LOG.debug('Cast %s to %s' % (asyncrequest.request_id, target.to_dict()))
        asyncrequest.result = 'Async request %s cast success' % rpc_method
        session.add(asyncrequest)
        session.flush()

        request_id = asyncrequest.request_id
        finishtime = asyncrequest.finishtime
        deadline = asyncrequest.deadline + 1
        expire = asyncrequest.expire
        if expire:
            storage = get_cache()
        else:
            storage = session

        def check_respone():
            wait = finishtime - int(time.time())
            if wait > 0:
                eventlet.sleep(wait)
            not_response_agents = set(wait_agents)

            not_overtime = 2
            while True:
                not_response_agents = responeutils.norespones(storage=storage,
                                                              request_id=request_id,
                                                              agents=not_response_agents)
                if not not_response_agents:
                    break
                if int(time.time()) > deadline:
                    not_overtime -= 1
                    if not not_overtime:
                        break
                eventlet.sleep(1)

            bulk_data = []
            agent_time = int(time.time())
            for agent_id in not_response_agents:
                data = dict(request_id=request_id,
                            agent_id=agent_id,
                            agent_time=agent_time,
                            resultcode=manager_common.RESULT_OVER_FINISHTIME,
                            result='Agent respone overtime')
                bulk_data.append(data)
            count = responeutils.bluk_insert(storage, bulk_data, expire)
            asyncrequest.status = manager_common.FINISH
            if count:
                asyncrequest.resultcode = manager_common.RESULT_NOT_ALL_SUCCESS
                asyncrequest.result = '%d agent not respone' % count
            else:
                asyncrequest.resultcode = manager_common.RESULT_SUCCESS
                asyncrequest.result = 'all agent respone result'
            session.flush()
            session.close()
        threadpool.add_thread(safe_func_wrapper, check_respone, LOG)

    def rpc_respone(self, ctxt, request_id, body):
        """agent report respone api"""
        session = get_session()
        asyncrequest = model_query(session, AsyncRequest, filter=AsyncRequest.request_id == request_id).one()
        if not asyncrequest.expire:
            return responeutils.agentrespone(session, request_id, body)
        else:
            return responeutils.agentrespone(get_cache(), request_id, body)
