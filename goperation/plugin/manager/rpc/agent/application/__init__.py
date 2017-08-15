from goperation.plugin.manager import common as manager_common
from goperation.plugin.manager.config import manager_group
from goperation.plugin.manager.rpc.agent.base import RpcAgentManager
from simpleutil.config import cfg
from simpleutil.log import log as logging
from simpleutil.utils import singleton
from simpleutil.utils.lockutils import PriorityLock

CONF = cfg.CONF

LOG = logging.getLogger(__name__)


@singleton.singleton
class ApplicationManager(RpcAgentManager):

    agent_type = manager_common.APPLICATION

    def __init__(self):
        RpcAgentManager.__init__(self)

