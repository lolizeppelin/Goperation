from simpleutil.config import cfg
from simpleservice.ormdb.config import database_opts

CONF = cfg.CONF

manager_group = cfg.OptGroup(name='manager', title='Manager options')
CONF.register_group(manager_group)

manager_opts = [
    cfg.MultiOpt('routes',
                 item_type=cfg.types.ImportString(),
                 default=None,
                 help='Manager extend route module string'),
]

CONF.register_opts(manager_opts, manager_group)

CONF.register_opts(database_opts, manager_group)

