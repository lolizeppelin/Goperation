from simpleutil.config import cfg

from glockredis .config import redis_opts

from simpleservice.ormdb.config import database_opts
from simpleservice.rpc.driver.config import rpc_base_opts
from simpleservice.rpc.driver.config import rabbit_opts
from simpleservice.rpc.driver.config import amqp_opts

from goperation.filemanager.config import filemanager_opts


CONF = cfg.CONF


manager_group = cfg.OptGroup(name='manager', title='Manager base options')
CONF.register_group(manager_group)

manager_rabbit_group = cfg.OptGroup(name='rabbit', title='Manager RabbitMQ driver options')
CONF.register_group(manager_rabbit_group)

filemanager_group = cfg.OptGroup(name='filemanager', title='FileManager options')
CONF.register_group(filemanager_group)

# database for manager
CONF.register_opts(database_opts, manager_group)
# redis for manager
CONF.register_opts(redis_opts, manager_group)
# rabbit for manager
CONF.register_opts(rpc_base_opts, manager_rabbit_group)
CONF.register_opts(amqp_opts, manager_rabbit_group)
CONF.register_opts(rabbit_opts, manager_rabbit_group)
# filemanager for manager
CONF.register_opts(filemanager_opts, filemanager_group)
# reset default value of rabbit_virtual_host
CONF.set_default('rabbit_virtual_host', default='goperation', group=manager_rabbit_group)
