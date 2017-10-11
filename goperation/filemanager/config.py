from simpleutil.config import cfg

CONF = cfg.CONF


filemanager_opts = [
    cfg.StrOpt('sqlite',
               default='$state_path/$filemanager.db',
               help='The SQLAlchemy connection string '
                    'to use to connect to the database.'),
    cfg.StrOpt('folder',
               help='File Manager save file folder'),
    cfg.HostnameOrIPOpt('files_url',
               help='Get file info from this url'),
    cfg.StrOpt('url_path',
               default='/files',
               help='Get file info api url path'),
    cfg.IntOpt('retrys',
               min=1,
               max=5,
               default=3,
               help='Retry times for http request'),
    cfg.IntOpt('timeout',
               default=3,
               help='Timeout of request get file url'),
]


