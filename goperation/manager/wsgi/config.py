from simpleutil.config import cfg

CONF = cfg.CONF

route_opts = [
    cfg.MultiImportStrOpt('routes',
                          default=[],
                          help='Private route module string'),
    cfg.MultiImportStrOpt('publics',
                          default=[],
                          help='Public route module string'),
]

def list_opts():
    return route_opts