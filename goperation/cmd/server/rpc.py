from simpleutil.config import cfg
from simpleutil.log import log as logging


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


def configure(config_files=None, config_dirs=None):
    from goperation.manager import common as manager_common
    from goperation import config as goperation_config

    # create a new project and group named gcenter
    name = manager_common.SERVER
    # init goperation config
    gcenter_group = goperation_config.configure(name, config_files, config_dirs)

    from simpleservice.rpc.config import rpc_server_opts
    from goperation.manager.rpc.server.config import gop_rpc_server_opts

    # set gcenter config
    CONF.register_opts(rpc_server_opts, group=gcenter_group)
    CONF.register_opts(gop_rpc_server_opts, group=gcenter_group)
    return CONF[gcenter_group.name]


def run(procname, config_files, config_dirs=None):
    conf = configure(config_files=config_files, config_dirs=config_dirs)

    from simpleservice.server import LaunchWrapper
    from simpleservice.server import launch
    from simpleservice.rpc.service import LauncheRpcServiceBase
    from goperation.manager.rpc.server import RpcServerManager
    from goperation import threadpool

    wrappers = []
    rpc_service = LauncheRpcServiceBase(RpcServerManager(),
                                        user=conf.rpc_user,
                                        group=conf.rpc_group,
                                        plugin_threadpool=threadpool)
    rpc_wrapper = LaunchWrapper(service=rpc_service, workers=conf.rpc_process)
    wrappers.append(rpc_wrapper)
    launch(wrappers, procname=procname)
