from simpleutil.config import cfg

from simpleservice.ormdb.config import database_opts
from simpleservice.rpc.driver.config import rpc_base_opts
from simpleservice.rpc.driver.config import rabbit_opts
from simpleservice.rpc.driver.config import amqp_opts

from goperation.redis.config import redis_opts

goperation_opts = [
    cfg.FloatOpt('glock_alloctime',
                 default=1.5,
                 help='Timeout for allocate glock')
]

CONF = cfg.CONF

manager_group = cfg.OptGroup(name='manager', title='Manager base options')
CONF.register_group(manager_group)

manager_rabbit_group = cfg.OptGroup(name='rabbit', title='Manager RabbitMQ driver options')
CONF.register_group(manager_rabbit_group)

# goperation opts for manager
CONF.register_opts(goperation_opts, manager_group)
# database for manager
CONF.register_opts(database_opts, manager_group)
# redis for manager
CONF.register_opts(redis_opts, manager_group)
# rabbit for manager
CONF.register_opts(rpc_base_opts, manager_rabbit_group)
CONF.register_opts(amqp_opts, manager_rabbit_group)
CONF.register_opts(rabbit_opts, manager_rabbit_group)
# reset default value of rabbit_virtual_host
CONF.set_default('rabbit_virtual_host', default='goperation', group=manager_rabbit_group)
