from simpleutil.config import cfg

redis_opts = [
    cfg.HostnameOpt('redis_host',
                    default='127.0.0.1',
                    help='Redis connect host address'),
    cfg.PortOpt('redis_port',
                default=6379,
                help='Redis connect Port'),
    cfg.IntOpt('redis_db',
               default=0,
               help='Redis datababse id'),
    cfg.StrOpt('redis_password',
               default=None,
               max_length=32,
               regex='^[a-zA-Z0-9_]+$',
               help='Redis password'),
    cfg.FloatOpt('redis_socket_timeout',
                 default=0.5,
                 help='Timeout for socket send and receive'),
    cfg.FloatOpt('redis_connect_timeout',
                 default=3.0,
                 help='Timeout for socket connect'),
    cfg.IntOpt('redis_pool_size',
               min=2,
               max=20,
               default=5,
               help='Maximum number of redis connections to keep open in a '
                    'pool.'),
    cfg.IntOpt('redis_heartbeat_overtime',
               default=300,
               max=10000,
               min=100,
               help='Millisecond between two heartbeat'),
    cfg.IntOpt('redis_heartbeat_overtime_max_count',
               default=3,
               max=5,
               min=1,
               help='Over time max count of redis_heartbeat_overtime'),
    cfg.StrOpt('redis_key_prefix',
               default='goper',
               max_length=12,
               regex='^[a-zA-Z0-9]+$',
               help='redis key prefix value')
]
