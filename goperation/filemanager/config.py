from simpleutil.config import cfg

CONF = cfg.CONF


filemanager_opts = [
    cfg.StrOpt('sqlite',
               default='$state_path/filemanager.db',
               help='File Manager storage file'),
    cfg.StrOpt('folder',
               help='File Manager save file folder')
]

def list_opts():
    return list(filemanager_opts)
