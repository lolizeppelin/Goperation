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


def find_paste_abs(conf):
    # isure paste_deploy config
    if not conf.paste_config:
        raise TypeError('Paste config is None')
    if not os.path.isabs(conf.paste_config):
        paste_path = CONF.find_file(conf.paste_config)
    else:
        paste_path = conf.paste_config
    if not paste_path:
        raise TypeError('Paste config is None')
    return paste_path