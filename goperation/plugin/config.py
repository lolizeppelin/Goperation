import os
import logging as defalut_logging

from simpleutil.log import log as logging
from simpleutil.config import cfg

from simpleservice import config as base_config

CONF = cfg.CONF

plugin_opts = [
    cfg.MultiOpt('endpoints',
                 default=[],
                 item_type=cfg.types.MultiImportString(),
                 help='The endpoints class')
]


redis_opts = [
    cfg.HostnameOpt('redis_host',
                    default='127.0.0.1',
                    help='Redis connect host address'),
    cfg.PortOpt('redis_post',
                default=6379,
                help='Redis connect Port'),
    cfg.IntOpt('redis_db',
               default=0,
               help='Redis datababse id'),
    cfg.StrOpt('redis_password',
               default=None,
               max_length=32,
               regex='^[a-zA-Z0-9_]+$',
               help='Redis password'),
    cfg.FloatOpt('redis_socket_timeout',
                 default=0.5,
                 help='Timeout before of socket send and receive'),
    cfg.FloatOpt('redis_connect_timeout',
                 default=3.0,
                 help='Timeout before of socket connect'),
    cfg.IntOpt('redis_pool_size',
               min=2,
               max=20,
               default=5,
               help='Maximum number of redis connections to keep open in a '
                    'pool.'),
    cfg.IntOpt('redis_heartbeat_overtime',
               default=300,
               max=10000,
               min=100,
               help='Time of between two heartbeat'),
    cfg.IntOpt('redis_heartbeat_overtime_max_count',
               default=3,
               max=5,
               min=1,
               help='Over time max count of redis_heartbeat_overtime'),
    cfg.StrOpt('redis_key_prefix',
               default='goperation',
               max_length=16,
               regex='^[a-zA-Z0-9]+$',
               help='')
]

def configure(name, default_log_levels=None):
    # set base config
    base_config.configure()
    # over write state path default value
    CONF.set_default('state_path', default='/var/run/goperation')
    # reg plugin opts
    CONF.register_opts(plugin_opts)
    # set log config
    logging.setup(CONF, name)
    defalut_logging.captureWarnings(True)
    if default_log_levels:
        base_config.set_default_for_default_log_levels(default_log_levels)
