from simpleutil.config import cfg

CONF = cfg.CONF


filemanager_opts = [
    cfg.StrOpt('sqlite',
               default='$state_path/filemanager.db',
               help='The SQLAlchemy connection string '
                    'to use to connect to the database.'),
    cfg.StrOpt('folder',
               help='File Manager save file folder'),
    cfg.HostnameOrIPOpt('files_api_address',
                        default='127.0.0.1',
                        help='Get file info from this address'),
    cfg.PortOpt('files_api_port',
                default=80,
                help='Api address listen port'),
    cfg.StrOpt('files_api_path',
               default='/files',
               help='Get file info url path'),
    cfg.IntOpt('retrys',
               min=1,
               max=5,
               default=3,
               help='Retry times for http request'),
    cfg.IntOpt('timeout',
               default=3,
               help='Timeout of request get file url'),
]
