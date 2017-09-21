import re
from goperation.manager import common as manager_common

regx_endpoint = re.compile('^[a-z][a-z0-9]+$', re.IGNORECASE)

def validate_endpoint(value):
    if not isinstance(value, basestring):
        raise ValueError('Entpoint name is not basestring')
    if len(value) > manager_common.MAX_ENDPOINT_NAME_SIZE:
        raise ValueError('Entpoint name over size')
    if not re.match(regx_endpoint, value):
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
