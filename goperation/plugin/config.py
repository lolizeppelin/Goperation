import logging as defalut_logging

from simpleutil.log import log as logging
from simpleutil.config import cfg

from simpleservice import config as base_config

CONF = cfg.CONF

plugin_opts = [
    cfg.MultiOpt('endpoints',
                 default=[],
                 item_type=cfg.types.MultiImportString(),
                 help='The endpoints class'),
    cfg.StrOpt('trusted',
               default='goperation-trusted-user',
               help='Trusted token, means a unlimit user'
               )
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
