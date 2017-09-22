from simpleutil.config import cfg
from simpleutil.log import log as logging
from simpleutil.utils import singleton
from simpleutil.utils import importutils

from goperation.manager import common as manager_common
from goperation.manager.rpc.agent import base
from goperation.manager.rpc.agent.config import rpc_endpoint_opts
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
        if CONF.endpoints:
            # endpoint class must be singleton
            for endpoint in CONF.endpoints:
                endpoint_group = cfg.OptGroup(endpoint.lower(),
                                              title='endpopint of %s' % endpoint)
                CONF.register_group(endpoint_group)
                CONF.register_opts(rpc_endpoint_opts, endpoint_group)
                endpoint_class = '%s.%s' % (CONF[endpoint_group].module,
                                            self.agent_type.capitalize())
                endpoint_class = importutils.import_class(endpoint_class)
                endpoint_kwargs = kwargs.get(endpoint_group.name, {})
                endpoint_kwargs.update({'manager': self,
                                        'group': endpoint_group})
                self.endpoints.add(endpoint_class(**endpoint_kwargs))

    @CheckManagerRpcCtxt
    @CheckEndpointRpcCtxt
    def call_endpoint(self, endpoint, method, ctxt, **kwargs):
        func = getattr(endpoint, method)
        return func(ctxt, **kwargs)
