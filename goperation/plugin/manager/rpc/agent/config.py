from goperation.plugin.manager import common as manager_common
from simpleutil.config import cfg

CONF = cfg.CONF

agent_group = cfg.OptGroup(name=manager_common.AGENT, title='AGENT base options group')
CONF.register_group(agent_group)


rpc_agent_opts = [
    cfg.HostnameOrIPOpt('gcenter',
                        help='Hostname or IP address of gcenter wsgi service'
                        ),
    cfg.IPOpt('local_ip',
              version=4,
              help='Rpc agent local ip address'),
    cfg.ListOpt('external_ips',
                default=[],
                item_type=cfg.types.IPAddress(version=4),
                help='External network IP addresses of this Rpc Agent'),
    cfg.PortRangeOpt('ports_range',
                     default=[],
                     help='Rpc agent can alloc port from this range'),
    cfg.FolderPathOpt('work_path',
                      help='Rpc agent work in this path, '
                           'And All Endpoint app install in this path'),
    cfg.IntOpt('online_report_interval',
               min=60,
               max=600,
               default=300,
               help='Rpc agent online report interval time in seconds'),
    cfg.BoolOpt('report_performance',
                default=False,
                help='Rpc agent online report with system performance'),
]
