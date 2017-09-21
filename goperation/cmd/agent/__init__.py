from simpleutil.config import cfg
from simpleutil.log import log as logging

from simpleservice.server import LaunchWrapper
from simpleservice.server import launch
from simpleservice.rpc.service import LauncheRpcServiceBase

from goperation import threadpool
from goperation import config as goperation_config


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


def configure(agent_type, config_files=None):
    agent_group = cfg.OptGroup(name=agent_type,
                               title='group of goperation %s agent' % agent_type)
    # init goperation config
    goperation_config.configure(agent_group, config_files)
    return agent_group.name


def run(manager_cls, config_files):
    configure(manager_cls.agent_type, config_files=config_files)
    wrappers = []
    rpc_service = LauncheRpcServiceBase(manager_cls(), plugin_threadpool=threadpool)
    rpc_wrapper = LaunchWrapper(service=rpc_service, workers=1)
    wrappers.append(rpc_wrapper)
    launch(wrappers)
