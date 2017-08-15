from goperation.plugin.manager import common as manager_common
from goperation.plugin.manager.rpc.agent.base import RpcAgentManager
from simpleutil.config import cfg
from simpleutil.log import log as logging
from simpleutil.utils import singleton
from simpleutil.utils.lockutils import PriorityLock

CONF = cfg.CONF

LOG = logging.getLogger(__name__)

@singleton.singleton
class SchedulerManager(RpcAgentManager):

    agent_type = manager_common.SCHEDULER

    def __init__(self):
        RpcAgentManager.__init__(selfs)
        # child process list
        self.childs = set()
        self.lock = PriorityLock()


    def full(self):
        return False

    def after_start(self):
        pass

    def after_stop(self):
        pass

    def initialize_service_hook(self):
         pass


    def call_endpoint(self, endpoint, method, ctxt, args):
        pass

    def rpc_async_request_check(self, ctxt, request_id, domain, agent_id):
        finishtime = ctxt.get('finishtime')
        deadline = ctxt.get('deadline')
        persist = ctxt.get('persist', 1)