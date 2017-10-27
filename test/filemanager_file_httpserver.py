# -*- coding: UTF-8 -*-
import os

import logging as defalut_logging
from simpleutil.config import cfg
from simpleutil.log import log as logging

from simpleservice import config as base_config
from simpleservice.wsgi.config import wsgi_options
from simpleservice.server import LaunchWrapper
from simpleservice.server import launch
from simpleservice.wsgi.service import load_paste_app
from simpleservice.wsgi.service import LauncheWsgiServiceBase


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


wsgi_base_group = cfg.OptGroup(name='filemanager', title='test filemanager api wsgi server')


def configure(version=None, config_files=None):
    base_config.configure()
    base_config.set_default_for_default_log_levels(['routes=INFO', ])
    CONF(project=wsgi_base_group.name, version=version,
         default_config_files=config_files)
    CONF.register_group(wsgi_base_group)
    logging.setup(CONF, wsgi_base_group.name)
    defalut_logging.captureWarnings(True)
    CONF.register_opts(wsgi_options, group=wsgi_base_group)
    CONF.set_default('paste_config', default='filemanager.ini', group=wsgi_base_group)
    if not CONF[wsgi_base_group.name].paste_config:
        LOG.critical('Paste config file not exist')
    if not os.path.isabs(CONF[wsgi_base_group.name].paste_config):
        paste_config = CONF.find_file(CONF[wsgi_base_group.name].paste_config)
    else:
        paste_config = CONF[wsgi_base_group.name].paste_config
    return paste_config


def run(topdir):
    if os.path.isdir(topdir):
        config_file = os.path.join(topdir, '%s.conf' % wsgi_base_group.name)
    else:
        config_file = topdir
    paste_config = configure(config_files=[config_file, ])
    name = wsgi_base_group.name
    app = load_paste_app(name, paste_config)
    wrappers = []
    wsgi_server = LauncheWsgiServiceBase(wsgi_base_group.name, app)
    wsgi_wrapper = LaunchWrapper(wsgi_server, CONF[wsgi_base_group.name].wsgi_process)
    wrappers.append(wsgi_wrapper)
    launch(wrappers, CONF[name].user, CONF[name].group)


def main():
    config_file = 'C:\\Users\\loliz_000\\Desktop\\etc\\filemanager\\filemanager.conf'
    run(config_file)


if __name__ == '__main__':
    main()
