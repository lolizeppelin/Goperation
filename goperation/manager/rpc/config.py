from simpleutil.config import cfg


rpc_server_opts = [
    cfg.StrOpt('rpc_user',
           default='root',
           help='Rpc Server run user'),
    cfg.StrOpt('rpc_group',
           default='root',
           help='Rpc Server run group'),
    cfg.IntOpt('rpc_process',
               default=1,
               min=1,
               help='The number of worker processes to serve the rpc process')
]


def list_opts():
    return rpc_server_opts