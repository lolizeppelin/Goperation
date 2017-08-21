from simpleutil.config import cfg
from simpleutil.log import log as logging

from simpleservice.server import LaunchWrapper
from simpleservice.server import launch
from simpleservice.rpc.service import LauncheRpcServiceBase

from goperation import plugin
from goperation.plugin import config as plugin_config


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


def configure(agent_type, config_files=None):
    agent_group = cfg.OptGroup(name=agent_type,
                               title='group of goperation %s agent' % agent_type)
    # init plugin config
    plugin_config.configure(agent_group, config_files)
    return agent_group.name


def run(manager, config_files):
    configure(manager.agent_type, config_files=config_files)
    wrappers = []
    rpc_service = LauncheRpcServiceBase(manager(), plugin_threadpool=plugin.threadpool)
    rpc_wrapper = LaunchWrapper(service=rpc_service, workers=1)
    wrappers.append(rpc_wrapper)
    launch(wrappers)
