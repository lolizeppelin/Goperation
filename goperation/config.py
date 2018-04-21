import os
import ConfigParser
import logging as defalut_logging

from simpleutil.log import log as logging
from simpleutil.config import cfg
from simpleutil.config import types
from simpleutil.utils import systemutils


from simpleservice import config as base_config

CONF = cfg.CONF

endpoint_load_opts = [
    cfg.ListOpt('endpoints',
                item_type=types.String(),
                help='The endpoint group name or namespace'),
]

service_base_opts = [
    cfg.IPOpt('local_ip',
              version=4,
              required=True,
              help='Goperation local ip address'),
    cfg.ListOpt('external_ips',
                item_type=cfg.types.IPAddress(version=4),
                default=[],
                help='Goperation external network IP addresses'),
    cfg.FolderPathOpt('work_path',
                      required=True,
                      help='Goperation work in this path'),
    cfg.StrOpt('repo',
               help='Goperation rpm repo address'),
]

def set_all_default():
    # over write state path default value
    from simpleservice.config import server_cli_opts
    cfg.set_defaults(server_cli_opts, state_path='/var/run/goperation')


def set_wsgi_default():
    # set default of paste config
    from simpleservice.wsgi.config import wsgi_server_options
    cfg.set_defaults(wsgi_server_options, paste_config='gcenter-paste.ini')

def set_rabbitmq_vhost_default():
    # set default of paste config
    from simpleservice.rpc.driver.config import rabbit_opts
    cfg.set_defaults(rabbit_opts, rabbit_virtual_host='goperation')


def configure(name, config_files, config_dirs=None):
    set_all_default()
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
    if systemutils.LINUX:
        if not CONF.repo:
            raise RuntimeError('rpm repo is not set')
        repofile = '/etc/yum.repos.d/goputil.repo'
        cf = ConfigParser.ConfigParser()
        if not os.path.exists(repofile):
            cf.add_section('goputil')
            cf.set('goputil', 'name', 'Goperation util rpm source')
            cf.set('goputil', 'baseurl', CONF.repo)
            cf.set('goputil', 'enabled', '1')
            cf.set('goputil', 'gpgcheck', '0')
            with open(repofile, 'wb') as f:
                cf.write(f)
        else:
            cf.read(repofile)
            if cf.get('goputil', 'baseurl') != CONF.repo:
                cf.set('goputil', 'baseurl', CONF.repo)
            with open(repofile, 'wb') as f:
                cf.write(f)
    return group


def list_opts():
    return endpoint_load_opts + service_base_opts
