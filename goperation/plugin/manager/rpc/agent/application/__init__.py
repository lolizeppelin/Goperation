from goperation.plugin.manager import common as manager_common
from goperation.plugin.manager.config import manager_group
from goperation.plugin.manager.rpc.agent.base import RpcAgentManager
from simpleutil.config import cfg
from simpleutil.log import log as logging
from simpleutil.utils import singleton
from simpleutil.utils.lockutils import PriorityLock

CONF = cfg.CONF

LOG = logging.getLogger(__name__)


@singleton
class ApplicationManager(RpcAgentManager):

    def __init__(self):
        RpcAgentManager.__init__(self, manager_common.APPLICATION)
        self.resource_lock = PriorityLock()
        self.resource_lock.set_defalut_priority(priority=5)


    def init_host(self, endpoints):
        super(ApplicationManager, self).init_host(endpoints)

    def alloc_ports(self, ports):
        """endpoint alloc ports"""
        pass

    def alloc_disk(self, size):
        """endpoint alloc disk"""
        pass