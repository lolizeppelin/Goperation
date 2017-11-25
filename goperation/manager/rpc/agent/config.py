from simpleutil.config import cfg


from goperation.manager import common as manager_common


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
    cfg.StrOpt('taskflow_storage',
               default='sqlite:///:memory:',
               help='simpleflow storage connection url'),
]

rpc_endpoint_opts = [
    cfg.ImportStringOpt('module',
                 help='Manager extend rpc endpoint module string'),
    cfg.IntOpt('max_lock',
                default=5,
                help='Endpoint max lock size'),
]
