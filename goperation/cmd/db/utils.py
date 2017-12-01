from simpleutil.config import cfg
from simpleservice.plugin.utils import init_plugin_database

from goperation.manager import models as manager_models


database_init_opts = [
    cfg.StrOpt('user',
               help='mysql database root user name'),
    cfg.StrOpt('passwd',
               help='mysql database root password'),
    cfg.StrOpt('host',
               help='mysql host or ipaddress'),
    cfg.PortOpt('port',
                 help='mysql server post'),
    cfg.StrOpt('schema',
               help='target mysql database schema')
]


def init_manager(db_info):
    init_plugin_database(db_info, manager_models)
