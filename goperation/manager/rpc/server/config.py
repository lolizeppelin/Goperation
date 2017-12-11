from simpleutil.config import cfg

CONF = cfg.CONF

gop_rpc_server_opts = [
    cfg.IntOpt('expire_time',
               min=2,
               max=20,
               default=10,
               help='Rpc agent status expire time'),
]

def list_opts():
    return gop_rpc_server_opts