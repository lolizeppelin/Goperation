import re
from simpleutil.utils import attributes
from goperation.manager import common as manager_common

illegal_endpoint_name = ['agent', 'port', 'endpoint', 'file', 'async', 'entity'
                         'flush', 'online', 'upgrade', 'active', 'status', 'clean',
                         'create', 'delete', 'edit', 'update', 'select', 'show', 'list',
                         'application', 'scheduler']

regx_endpoint = re.compile('^[a-z][a-z0-9]+$', re.IGNORECASE)

def validate_endpoint(value):
    if not value:
        raise ValueError('Entpoint name is empty')
    if not isinstance(value, basestring):
        raise ValueError('Entpoint name is not basestring')
    if len(value) > manager_common.MAX_ENDPOINT_NAME_SIZE:
        raise ValueError('Entpoint name over size')
    if not re.match(regx_endpoint, value):
        raise ValueError('Entpoint name %s not match regx' % value)
    return value.lower()


def validate_endpoints(value):
    if isinstance(value, basestring):
        if ',' in value:
            value = list(set(value.split(',')))
        else:
            return [validate_endpoint(value)]
    if isinstance(value, (list, tuple)):
        endpoints = set()
        for endpoint in value:
            endpoints.add(validate_endpoint(endpoint))
        return list(endpoints)
    raise ValueError('Entpoint list type error')

