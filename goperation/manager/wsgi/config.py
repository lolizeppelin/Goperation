from simpleutil.config import cfg

CONF = cfg.CONF

route_opts = [
    cfg.MultiImportStrOpt('routes',
                          default=[],
                          help='Extend route module string'),
    cfg.MultiImportStrOpt('auths',
                          default=[],
                          help='Authentication route module string'),
]

def list_opts():
    return route_opts