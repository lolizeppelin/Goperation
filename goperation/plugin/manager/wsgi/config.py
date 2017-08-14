from simpleutil.config import cfg

CONF = cfg.CONF

route_opts = [
    cfg.MultiOpt('routes',
                 item_type=cfg.types.MultiImportString(),
                 default=[],
                 help='Manager extend route module string'),
]
