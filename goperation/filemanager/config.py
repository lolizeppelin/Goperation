from simpleutil.config import cfg

CONF = cfg.CONF


filemanager_opts = [
    cfg.StrOpt('sqlite',
               default='$state_path/filemanager.db',
               help='The SQLAlchemy connection string '
                    'to use to connect to the database.'),
    cfg.StrOpt('folder',
               help='File Manager save file folder')
]

def list_opts():
    return list(filemanager_opts)
