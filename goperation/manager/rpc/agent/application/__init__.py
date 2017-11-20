from simpleutil.config import cfg
from simpleutil.log import log as logging
from simpleutil.utils import singleton

from goperation.manager import common as manager_common
from goperation.manager.rpc.agent import base
from goperation.manager.rpc.agent.ctxtdescriptor import CheckEndpointRpcCtxt
from goperation.manager.rpc.agent.ctxtdescriptor import CheckManagerRpcCtxt

CONF = cfg.CONF

LOG = logging.getLogger(__name__)


@singleton.singleton
class ApplicationManager(base.RpcAgentManager):

    agent_type = manager_common.APPLICATION

    def __init__(self, **kwargs):
        base.LOG = LOG
        super(ApplicationManager, self).__init__()

    @CheckManagerRpcCtxt
    @CheckEndpointRpcCtxt
    def call_endpoint(self, endpoint, method, ctxt, **kwargs):
        func = getattr(endpoint, method)
        return func(ctxt, **kwargs)
