from simpleutil.config import cfg

from simpleservice.ormdb.config import database_opts
from simpleservice.rpc.driver.config import rpc_base_opts
from simpleservice.rpc.driver.config import rabbit_opts
from simpleservice.rpc.driver.config import amqp_opts
from simpleservice.rpc.driver.config import rpc_client_opts

from goperation import config as goperation_config
from goperation.redis.config import redis_opts

from goperation.manager import common

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
    cfg.StrOpt('trusted',
               default='goperation-trusted-token',
               help='Trusted token, means a unlimit user'
               ),
]

manager_group = cfg.OptGroup(name=common.NAME,
                             title='Manager base options')

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
goperation_config.set_rabbitmq_vhost_default()
rabbit_conf = CONF[rabbit_group.name]


def list_manager_opts():
    return goperation_opts + database_opts + redis_opts
