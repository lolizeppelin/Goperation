from simpleutil.config import cfg

CONF = cfg.CONF

gop_rpc_server_opts = [
    cfg.IntOpt('expire_time',
               min=2,
               max=20,
               default=10,
               help='Rpc agent status expire time'),
    cfg.MultiImportStrOpt('executers',
                          default=['http'],
                          help='Rpc server executer class list'),
    cfg.MultiImportStrOpt('conditions',
                          default=['agents', 'entitys'],
                          help='Rpc server conditions class list'),
]

def list_opts():
    return gop_rpc_server_opts