from simpleutil.config import cfg

from goperation.manager import common as manager_common
from goperation.filemanager.config import filemanager_opts


CONF = cfg.CONF

agent_group = cfg.OptGroup(name=manager_common.AGENT, title='AGENT base options group')
CONF.register_group(agent_group)


rpc_agent_opts = [
    cfg.MultiOpt('ports_range',
                 item_type=cfg.types.PortRange(),
                 help='Rpc agent can alloc port from this range'),
    cfg.IntOpt('online_report_interval',
               min=1,
               max=10,
               default=5,
               help='Rpc agent online report interval time in minute'),
    cfg.BoolOpt('report_performance',
                default=False,
                help='Rpc agent online report with system performance'),
    cfg.StrOpt('taskflowcache',
               default='$work_path/taskflowcache',
               help='simpleflow storage file dir'),
    cfg.BoolOpt('ramfscache',
                default=False,
                help='taskflow cache file in ramfs',
                ),
    cfg.StrOpt('taskflow_connection',
                help='taskflow storage connection url, '
                     'taskflowcache option will be ignore when this option set'),
]

rpc_endpoint_opts = [
    cfg.ImportStringOpt('module',
                 help='Manager extend rpc endpoint module string'),
    cfg.IntOpt('max_lock',
                default=5,
                help='Endpoint max lock size'),
]


CONF.register_opts(rpc_agent_opts, agent_group)
CONF.register_opts(filemanager_opts, agent_group)


def list_opts():
    return rpc_agent_opts + filemanager_opts