import os
from simpleutil.config import cfg

CONF = cfg.CONF

route_opts = [
    cfg.MultiOpt('routes',
                 item_type=cfg.types.MultiImportString(),
                 default=[],
                 help='Manager extend route module string'),
]

def find_paste_abs(conf):
    # isure paste_deploy config
    if not conf.paste_config:
        raise TypeError('Paste config is None')
    if not os.path.isabs(conf.paste_config):
        paste_path = CONF.find_file(conf.paste_config)
    else:
        paste_path = conf.paste_config
    if not paste_path:
        raise TypeError('Paste config is None')
    return paste_path
