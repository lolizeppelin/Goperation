import os
import logging as defalut_logging

from simpleutil.log import log as logging
from simpleutil.config import cfg

from simpleservice import config as base_config

CONF = cfg.CONF

def configure(name, log_levels=None):
    # set base config
    base_config.configure()
    # over write state_path
    CONF.set_default('state_path', default='/var/run/goperation')

    # register manager opt
    manager_entity = cfg.Opt('manager_entity',
                             type=cfg.types.ImportString(),
                             default='goperation.plugin.manager.config.manager_group',
                             help='The manager defalut opts and group')

    CONF.register_opt(manager_entity)

    # register endpoints opt
    endpoints_entity = cfg.MultiOpt('endpoints',
                                    item_type=cfg.types.ImportString(),
                                    help='The endpoint list that Server will run')
    CONF.register_opt(endpoints_entity)
    # set log config
    logging.setup(CONF, name)
    defalut_logging.captureWarnings(True)
    if log_levels:
        base_config.set_default_for_default_log_levels(log_levels)


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