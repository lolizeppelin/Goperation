from simpleutil.config import cfg

from goperation.manager import common as manager_common
from goperation.filemanager.config import filemanager_opts


CONF = cfg.CONF

agent_group = cfg.OptGroup(name=manager_common.AGENT, title='Agent base options group')
CONF.register_group(agent_group)


rpc_agent_opts = [
    cfg.StrOpt('zone',
               default='all',
               regex='^[a-z][a-z0-9]+$',
               help='Agent zone mark'),
    cfg.MultiOpt('ports_range',
                 item_type=cfg.types.PortRange(),
                 help='Rpc agent can alloc port from this range'),
    cfg.IntOpt('online_report_interval',
               default=5,
               choices=[1, 3, 4, 5, 6, 10, 12, 15, 20, 30, 60],
               help='Rpc agent online report interval time in minute'),
    cfg.BoolOpt('report_performance',
                default=True,
                help='Rpc agent online report with system performance'),
    cfg.BoolOpt('metadata_flush_probability',
                min=1,
                default=10,
                help='Agent metadata flush cache probability, 10 means 1/10'),
    cfg.StrOpt('taskflowcache',
               default='$work_path/taskflowcache',
               help='simpleflow storage file dir'),
    cfg.BoolOpt('ramfscache',
                default=False,
                help='taskflow cache file in ramfs',
                ),
    cfg.StrOpt('taskflow_connection',
               help='taskflow storage connection url, taskflowcache '
                    'option will be ignore when this option set'),
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
