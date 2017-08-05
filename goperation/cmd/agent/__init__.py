from simpleutil.config import cfg
from simpleutil.log import log as logging
from simpleutil.utils import importutils

from simpleservice.server import ServerWrapper
from simpleservice.server import launch
from simpleservice.rpc.service import LauncheRpcServiceBase

from goperation import plugin
from goperation.plugin import config as plugin_config


CONF = cfg.CONF
LOG = logging.getLogger(__name__)

def configure(agent_group, config_files=None):
    # create a new project and group named gcenter
    CONF(project=agent_group.name,
         default_config_files=config_files)
    CONF.register_group(agent_group)
    # init some plugin config
    plugin_config.configure(agent_group.name)
    # set endpoint config
    if CONF.endpoints:
        for endpoint in CONF.endpoints:
            endpoint_group = importutils.import_class(endpoint)
            # add endpoint extent rpc
            for rpc in CONF[endpoint_group.name].rpc:
                plugin.EXTEND_RPC.append(importutils.import_class(rpc))
    return agent_group.name


def run(manager, config_files):
    aplication_group = cfg.OptGroup(name=manager.agent_type,
                                    title='group of goperation %s agent' % manager.agent_type)
    configure(aplication_group, config_files=config_files)
    servers = []
    rpc_server = LauncheRpcServiceBase(manager, CONF.endpoints)
    rpc_wrapper = ServerWrapper(rpc_server, 1)
    servers.append(rpc_wrapper)
    launch(servers, CONF.user, CONF.group)