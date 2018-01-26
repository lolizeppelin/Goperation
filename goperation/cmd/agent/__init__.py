from simpleutil.config import cfg
from simpleutil.log import log as logging


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


def configure(agent_type, config_files=None, config_dirs=None):
    from goperation import config as goperation_config
    # init goperation config
    goperation_config.configure(agent_type, config_files, config_dirs)


def run(procname, manager_cls, config_files, config_dirs=None):
    configure(manager_cls.agent_type,
              config_files=config_files, config_dirs=config_dirs)

    from goperation import threadpool
    from simpleservice.server import LaunchWrapper
    from simpleservice.server import launch
    from simpleservice.rpc.service import LauncheRpcServiceBase

    wrappers = []
    rpc_service = LauncheRpcServiceBase(manager_cls(), plugin_threadpool=threadpool)
    rpc_wrapper = LaunchWrapper(service=rpc_service, workers=1)
    wrappers.append(rpc_wrapper)
    launch(wrappers, procname)
