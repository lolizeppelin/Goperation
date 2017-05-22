from simpleutil.config import cfg
from simpleservice.ormdb.config import database_opts

CONF = cfg.CONF

manager_group = cfg.OptGroup(name='manager', title='Manager group')

CONF.register_group(manager_group)
CONF.register_opts(database_opts, manager_group)

