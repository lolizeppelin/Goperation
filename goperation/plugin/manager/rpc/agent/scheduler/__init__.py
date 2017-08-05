from goperation.plugin.manager import common
from goperation.plugin.manager.rpc.agent.base import RpcAgentManager
from simpleutil.config import cfg
from simpleutil.log import log as logging
from simpleutil.utils import singleton
from simpleutil.utils.lockutils import PriorityLock

CONF = cfg.CONF

LOG = logging.getLogger(__name__)

@singleton
class SchedulerManager(RpcAgentManager):

    def __init__(self):
        RpcAgentManager.__init__(self, common.SCHEDULER)
        # child process list
        self.childs = set()
        self.lock = PriorityLock()

    def init_host(self, endpoints):
        super(SchedulerManager, self).init_host(endpoints)

    def full(self):
        return False

    def after_start(self):
        pass

    def after_stop(self):
        pass

    def initialize_service_hook(self, rpcservice):
         self.endpoints = rpcservice.endpoints


    def call_endpoint(self, endpoint, method, ctxt, args):
        pass

    def rpc_async_request_check(self, ctxt, request_id, domain, agent_id):
        finishtime = ctxt.get('finishtime')
        deadline = ctxt.get('deadline')
        persist = ctxt.get('persist', 1)