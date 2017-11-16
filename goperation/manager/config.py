from simpleutil.config import cfg

from simpleservice.ormdb.config import database_opts
from simpleservice.rpc.driver.config import rpc_base_opts
from simpleservice.rpc.driver.config import rabbit_opts
from simpleservice.rpc.driver.config import amqp_opts

from goperation.redis.config import redis_opts

CONF = cfg.CONF


goperation_opts = [
    cfg.StrOpt('rabbit',
               default='Manager rabbitmq config group name',
               help=''
               ),
    cfg.FloatOpt('glock_alloctime',
                 default=3,
                 help='Timeout for allocate glock'),
    cfg.HostnameOrIPOpt('gcenter',
                        help='Hostname or IP address of gcenter wsgi service'
                        ),
    cfg.PortOpt('gcenter_port',
                default=7999,
                help='Http port of gcenter wsgi service'),
    cfg.IntOpt('http_pconn_count',
               min=5,
               max=50,
               default=30,
               help='HTTP persistent connection number for gcenter'),
    cfg.StrOpt('trusted',
               default='goperation-trusted-user',
               help='Trusted token, means a unlimit user'
               ),
]

manager_group = cfg.OptGroup(name='manager', title='Manager base options')
CONF.register_group(manager_group)
# goperation opts for manager
CONF.register_opts(goperation_opts, manager_group)
# database for manager
CONF.register_opts(database_opts, manager_group)
# redis for manager
CONF.register_opts(redis_opts, manager_group)
# rabbit for manager
CONF.register_opts(rpc_base_opts, manager_group)
CONF.register_opts(amqp_opts, manager_group)
CONF.register_opts(rabbit_opts, manager_group)
# reset default value of rabbit_virtual_host
CONF.set_default('rabbit_virtual_host', default='goperation', group=manager_group)
