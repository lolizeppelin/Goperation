from simpleutil.config import cfg
from simpleutil.log import log as logging

from simpleservice.plugin.base import ManagerBase

from goperation.plugin.manager.targetutils import target_server
from goperation.plugin.manager.api import get_session


CONF = cfg.CONF

LOG = logging.getLogger(__name__)


class RpcServerManager(ManagerBase):

    def __init__(self, agent_type):
        self.agent_type = agent_type
        ManagerBase.__init__(self,
                             target=target_server(agent_type, CONF.host))

        self.session = get_session()
        self.rsession = get_session(readonly=True)

    def init_host(self):
        pass

    def after_stop(self):
        pass

    def initialize_service_hook(self, rpcservice):
        # check endpoint here
        pass

    def full(self):
        return False

    def rpc_show(self, ctxt, args):
        print 'get rpc show', ctxt, args
        return {'ret': 'rpc show success'}
