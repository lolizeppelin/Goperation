from simpleutil.config import cfg

from simpleservice.ormdb.config import database_opts
from simpleservice.rpc.driver.config import rpc_base_opts
from simpleservice.rpc.driver.config import rabbit_opts
from simpleservice.rpc.driver.config import amqp_opts
from simpleservice.rpc.config import rpc_client_opts

from goperation.redis.config import redis_opts

CONF = cfg.CONF


goperation_opts = [
    cfg.FloatOpt('glock_alloctime',
                 default=3,
                 help='Timeout for allocate glock'),
    cfg.HostnameOrIPOpt('gcenter',
                        default='127.0.0.1',
                        help='Hostname or IP address of gcenter wsgi service'),
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
manager_conf = CONF[manager_group.name]

# rabbit for manager
rabbit_group = cfg.OptGroup(name='rabbit', title='Manager RabbitMQ base group')
CONF.register_opts(rpc_base_opts, rabbit_group)
CONF.register_opts(amqp_opts, rabbit_group)
CONF.register_opts(rabbit_opts, rabbit_group)
CONF.register_opts(rpc_client_opts, rabbit_group)
# reset default value of rabbit_virtual_host
CONF.set_default('rabbit_virtual_host', default='goperation', group=rabbit_group)
rabbit_conf = CONF[rabbit_group.name]
