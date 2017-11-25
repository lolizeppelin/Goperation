import logging as defalut_logging

from simpleutil.log import log as logging
from simpleutil.config import cfg

from simpleservice import config as base_config

CONF = cfg.CONF

service_base_opts = [
    cfg.MultiOpt('endpoints',
                 default=[],
                 item_type=cfg.types.String(),
                 help='The endpoint group name or namespace'),
    cfg.IPOpt('local_ip',
              version=4,
              help='Goperation local ip address'),
    cfg.ListOpt('external_ips',
                default=[],
                item_type=cfg.types.IPAddress(version=4),
                help='Goperation external network IP addresses'),
    cfg.FolderPathOpt('work_path',
                      help='Goperation work in this path'),
]


def configure(group, config_files, config_dirs=None, default_log_levels=None):
    args = None
    if config_dirs is not None:
        args = []
        if isinstance(config_dirs, basestring):
            config_dirs = [config_dirs, ]
        for _dir in config_dirs:
            args.extend(['--config-dir', _dir])
    if isinstance(config_files, basestring):
        config_files = [config_files, ]
    CONF(args=args,
         project=group.name,
         default_config_files=config_files)
    CONF.register_group(group)
    # set base config
    base_config.configure()
    # over write state path default value
    CONF.set_default('state_path', default='/var/run/goperation')
    # reg base opts
    CONF.register_opts(service_base_opts)
    # set log config
    logging.setup(CONF, group.name)
    defalut_logging.captureWarnings(True)
    if default_log_levels:
        base_config.set_default_for_default_log_levels(default_log_levels)
