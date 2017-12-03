from simpleutil.config import cfg

CONF = cfg.CONF


filemanager_opts = [
    cfg.FolderPathOpt('filecache',
               default='$work_path/filecache',
               help='File Manager working folder'),
]

def list_opts():
    return list(filemanager_opts)
