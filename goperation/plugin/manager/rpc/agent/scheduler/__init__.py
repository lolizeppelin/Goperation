from simpleutil.config import cfg
from simpleutil.log import log as logging
from simpleutil.utils import singleton

from goperation.plugin.manager import common
from goperation.plugin.manager.rpc.base import RpcServerManager

CONF = cfg.CONF

LOG = logging.getLogger(__name__)

@singleton
class SchedulerManager(RpcServerManager):

    def __init__(self):
        RpcServerManager.__init__(self, common.SCHEDULER)
