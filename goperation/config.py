import logging as defalut_logging

from simpleutil.log import log as logging
from simpleutil.config import cfg

from simpleservice import config as base_config

CONF = cfg.CONF

service_base_opts = [
    cfg.MultiStrOpt('endpoints',
                    help='The endpoint group name or namespace'),
    cfg.IPOpt('local_ip',
              version=4,
              required=True,
              help='Goperation local ip address'),
    cfg.ListOpt('external_ips',
                item_type=cfg.types.IPAddress(version=4),
                help='Goperation external network IP addresses'),
    cfg.FolderPathOpt('work_path',
                      required=True,
                      help='Goperation work in this path'),
]

def set_all_default():
    # over write state path default value
    from simpleservice.config import default_opts
    from simpleutil.log._options import logging_cli_opts
    cfg.set_defaults(logging_cli_opts, log_dir='/var/log/goperation')
    cfg.set_defaults(default_opts, state_path='/var/run/goperation')


def set_wsgi_default():
    # set default of paste config
    from simpleservice.wsgi.config import wsgi_server_options
    cfg.set_defaults(wsgi_server_options, paste_config='gcenter-paste.ini')

def set_rabbitmq_vhost_default():
    # set default of paste config
    from simpleservice.rpc.driver.config import rabbit_opts
    cfg.set_defaults(rabbit_opts, rabbit_virtual_host='goperation')


def configure(name, config_files, config_dirs=None):
    group = cfg.OptGroup(name=name, title='group of goperation %s' % name)
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
    # reg base opts
    CONF.register_opts(service_base_opts)
    # set log config
    logging.setup(CONF, group.name)
    defalut_logging.captureWarnings(True)
    set_all_default()
    return group


def list_opts():
    return service_base_opts
