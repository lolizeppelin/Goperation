from simpleutil.config import cfg
from simpleutil.config import types

CONF = cfg.CONF

authfilter_opts = [
    cfg.ListOpt('allowed_trusted_ip',
                item_type=types.IPAddress(version=4),
                default=[],
                help='Allowed ipaddress without token'),
    cfg.BoolOpt('allowed_same_subnet',
                help='Allow ipaddress without token in same subnet'),
    cfg.HostnameOpt('allowed_hostname',
                    help='Allow hostname'),
    cfg.IntOpt('token_cache_size',
               default=25,
               min=10,
               max=250,
               help='Token cache dict size')
]

cors_opts = [
    cfg.ListOpt('allowed_origin',
                default=["*"],
                help='Indicate whether this resource may be shared with the '
                     'domain received in the requests "origin" header.'),
    cfg.BoolOpt('allow_credentials',
                default=True,
                help='Indicate that the actual request can include user '
                     'credentials'),
    cfg.ListOpt('expose_headers',
                default=['Content-Type', 'Cache-Control', 'Content-Language',
                         'Expires', 'Last-Modified', 'Pragma'],
                help='Indicate which headers are safe to expose to the API. '
                     'Defaults to HTTP Simple Headers.'),
    cfg.IntOpt('max_age',
               default=3600,
               help='Maximum cache age of CORS preflight requests.'),
    cfg.ListOpt('allow_methods',
                default=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS', 'UPDATE', 'HEAD'],
                help='Indicate which methods can be used during the actual '
                     'request.'),
    cfg.ListOpt('allow_headers',
                default=['Content-Type', 'Cache-Control', 'Content-Language',
                         'Expires', 'Last-Modified', 'Pragma', 'Auth-Token'],
                help='Indicate which header field names may be used during '
                     'the actual request.')
]


def list_opts():
    return authfilter_opts + cors_opts
