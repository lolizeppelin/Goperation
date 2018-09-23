# -*- coding: UTF-8 -*-

import logging as default_logging
from simpleutil.config import cfg
from simpleutil.log import log as logging

from simpleutil.utils.threadgroup import ThreadGroup

from simpleservice import config as base_config


from goperation.filemanager import TargetFile
from goperation.filemanager import FileManager
from goperation.filemanager.config import filemanager_opts


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


fmclient_group = cfg.OptGroup(name='fmclient', title='test filemanager api wsgi server')


def configure(version=None, config_files=None):
    base_config.configure()
    CONF(project=fmclient_group.name, version=version,
         default_config_files=config_files)
    CONF.register_group(fmclient_group)
    logging.setup(CONF, fmclient_group.name)
    default_logging.captureWarnings(True)
    CONF.register_opts(filemanager_opts, group=fmclient_group)


def main():
    config_file = 'C:\\Users\\loliz_000\\Desktop\\etc\\filemanager\\filemanager.conf'
    configure(config_files=[config_file])
    pool = ThreadGroup(10)
    fmclient = FileManager(conf=CONF.fmclient,
                           rootpath=r'C:\Users\loliz_000\Desktop\etc',
                           threadpool=pool)
    fmclient.scanning(strict=False)
    target = TargetFile('41l41')
    fmclient.get(target)

if __name__ == '__main__':
    main()
