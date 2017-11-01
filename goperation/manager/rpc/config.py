from simpleutil.config import cfg
from goperation.filemanager.config import filemanager_opts

CONF = cfg.CONF

filemanager_group = cfg.OptGroup(name='filemanager', title='FileManager options')
CONF.register_group(filemanager_group)
# filemanager for manager
CONF.register_opts(filemanager_opts, filemanager_group)