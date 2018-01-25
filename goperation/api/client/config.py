from simpleutil.config import cfg

client_opts = [
    cfg.HostnameOrIPOpt('gcenter',
                        default='127.0.0.1',
                        help='Hostname or IP address of gcenter wsgi service'),
    cfg.PortOpt('gcenter_port',
                default=7999,
                help='Http port of gcenter wsgi service'),
    cfg.StrOpt('trusted',
               default='goperation-trusted-token',
               help='Trusted token, means a unlimit user'
               ),
    cfg.IntOpt('retry',
               default=3,
               help='Http client retry times'
               ),
    cfg.IntOpt('apitimeout',
               default=3,
               help='Http client request timeout'
               ),
]
