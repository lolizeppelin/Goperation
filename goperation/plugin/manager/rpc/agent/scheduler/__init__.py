import time
import eventlet

from simpleutil.config import cfg
from simpleutil.log import log as logging
from simpleutil.utils import singleton

from simpleservice.rpc.target import Target
from simpleservice.rpc.result import BaseRpcResult
from simpleservice.rpc.driver.exceptions import AMQPDestinationNotFound

from simpleservice.ormdb.api import model_query

from goperation import plugin
from goperation.plugin.utils import safe_fun_wrapper
from goperation.plugin.manager import common as manager_common
from goperation.plugin.manager.api import get_session
from goperation.plugin.manager.api import get_client
from goperation.plugin.manager.models import AsyncRequest
from goperation.plugin.manager.models import AgentRespone

from goperation.plugin.manager.rpc.agent.base import RpcAgentManager
from goperation.plugin.manager.rpc.ctxtdescriptor import CheckManagerRpcCtxt
from goperation.plugin.manager.rpc.ctxtdescriptor import CheckThreadPoolRpcCtxt


CONF = cfg.CONF

LOG = logging.getLogger(__name__)

@singleton.singleton
class SchedulerManager(RpcAgentManager):

    agent_type = manager_common.SCHEDULER

    def __init__(self):
        super(SchedulerManager, self).__init__()


    def resopne_checker(self):
        pass


    @CheckManagerRpcCtxt
    @CheckThreadPoolRpcCtxt
    # def asyncrequest(self, ctxt, **kwargs):
    def asyncrequest(self, ctxt,
                     asyncrequest, rpc_target, rpc_method,
                     rpc_ctxt, rpc_args):
        wait_agents = set(rpc_ctxt.get('agents'))
        asyncrequest = AsyncRequest(**asyncrequest)
        asyncrequest.scheduler = self.agent_id
        target = Target(**rpc_target)
        with self.work_lock:
            session = get_session()
            rpc = get_client()
            try:
                rpc.cast(target, ctxt=rpc_args, msg={'method': rpc_method, 'args': rpc_args})
            except AMQPDestinationNotFound:
                asyncrequest.resultcode = manager_common.SEND_FAIL
                asyncrequest.result = 'Async %s request send fail, AMQPDestinationNotFound' % rpc_method
                asyncrequest.status = manager_common.FINISH
                session.add(asyncrequest)
                session.flush()
                return BaseRpcResult(self.agent_id, resultcode=manager_common.RESULT_ERROR,
                                     result=asyncrequest.result)
            asyncrequest.result = 'Async request %s cast success' % rpc_method
            session.add(asyncrequest)
            session.flush()

            def check_respone():
                now = int(time.time())
                wait_time = asyncrequest.finishtime - now
                if wait_time > 0:
                    eventlet.sleep(wait_time)
                query = model_query(get_session(readonly=True),
                                    AgentRespone.agent_id,
                                    filter=AgentRespone.request_id == asyncrequest.request_id)
                while True:
                    finish_agents = set()
                    for row in query:
                        finish_agents.add(row[0])
                    if finish_agents == wait_agents:
                        return
                    if int(time.time()) > asyncrequest.deadline:
                        agents_over_deadline = wait_agents - finish_agents
                        self.client.scheduler_overtime_respone(asyncrequest.request_id,
                                                               {'agents': agents_over_deadline})
                        if finish_agents - wait_agents:
                            LOG.warning('Finished async request agent more then agents in ctxt')
                            LOG.debug('Agent %s is finished, but not in ctxt' % str(finish_agents - wait_agents))
                        return
                    eventlet.sleep(0.25)

            plugin.threadpool.add_thread(safe_fun_wrapper, check_respone, LOG)
            return BaseRpcResult(self.agent_id, resultcode=manager_common.RESULT_SUCCESS,
                                     result=asyncrequest.result)




