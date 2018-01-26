from simpleutil.config import cfg
from simpleutil.config import types

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
    cfg.IntOpt('retries',
               default=3,
               help='Http client retry times'
               ),
    cfg.IntOpt('apitimeout',
               default=5,
               help='Http client request timeout'
               ),
]

index_opts = [
    cfg.IntOpt('page_num',
               default=0,
               help='Bluk select results page number'
               ),
    cfg.StrOpt('order',
               default=None,
               help='Bluk select results order key'
               ),
    cfg.BoolOpt('desc',
                default=False,
                help='Bluk select results order desc'
                ),
]
