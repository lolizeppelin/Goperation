from simpleutil.config import cfg
from simpleutil.config import types

CONF = cfg.CONF

authfilter_opts = [
    cfg.ListOpt('allowed_trusted_ip',
                item_type=types.IPAddress(version=4),
                default=[],
                help='Trusted token limit ipaddress'),
    cfg.HostnameOpt('allowed_hostname',
                    help='Allow hostname'),
    cfg.IntOpt('token_cache_size',
               default=25,
               min=10,
               max=250,
               help='Token cache dict size')
]


def list_opts():
    return authfilter_opts
