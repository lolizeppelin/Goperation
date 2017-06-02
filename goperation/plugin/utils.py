import re

from glockredis.client import Redis

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


def redis(server_id, conf):
    kwargs = dict(server_id=server_id,
                  max_connections=conf.redis_pool_size,
                  host=conf.redis_host,
                  port=conf.redis_post,
                  db=conf.redis_db,
                  password=conf.redis_password,
                  socket_connect_timeout=conf.redis_connect_timeout,
                  socket_timeout=conf.redis_socket_timeout,
                  heart_beat_over_time=conf.redis_heartbeat_overtime,
                  heart_beat_over_time_max_count=conf.redis_heartbeat_overtime_max_count,
                  )
    return Redis.from_url(**kwargs)
