from simpleutil.config import cfg
from simpleutil.log import log as logging

from simpleservice.plugin.base import ManagerBase
from simpleservice.rpc.target import Target

from goperation.plugin.manager.dbapi import get_session
from goperation.plugin.manager import manager_group



CONF = cfg.CONF

LOG = logging.getLogger(__name__)



class RpcServerManager(ManagerBase):

    def __init__(self, rpc_type):
        self.rpc_type = rpc_type
        ManagerBase.__init__(self,
                             target=Target(topic='agent.%s' % self.rpc_type,
                                           namespace=manager_group.name))
        self.session = get_session()
        self.rsession = get_session(readonly=True)

    def init_host(self):
        if self.target.server is None:
            self.target.server = CONF.host

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
