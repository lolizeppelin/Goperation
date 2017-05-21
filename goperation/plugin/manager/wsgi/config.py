from simpleutil.config import cfg
from goperation.plugin.manager.config import manager_group

CONF = cfg.CONF

routes_opts = [
    cfg.MultiStrOpt('routes',
                    item_type=cfg.types.ImportString(),
                    default=[],
                    help='Manager extend route module string'),
]

CONF.register_opts(routes_opts, manager_group)