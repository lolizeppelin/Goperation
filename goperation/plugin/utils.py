import re
from goperation.plugin import common as plugin_common


def validate_endpoint(value):
    if not isinstance(value, basestring):
        raise ValueError('Entpoint name is not basestring')
    if len(value) > plugin_common.MAX_HOST_NAME_SIZE:
        raise ValueError('Entpoint name over size')
    if not re.match(plugin_common.regx_endpoint, value):
        raise ValueError('Entpoint name %s not match regx' % value)
    return value.lower()


def validate_endpoints(value):
    if isinstance(value, basestring):
        return [validate_endpoint(value)]
    if isinstance(value, (list, tuple)):
        endpoints = set()
        for endpoint in value:
            endpoints.add(validate_endpoint(endpoint))
        return list(endpoints)
    raise ValueError('Entpoint list type error')
