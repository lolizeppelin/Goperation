from simpleutil.config import cfg

from simpleservice.rpc.target import Target

from goperation.manager.common import AGENT
from goperation.manager.common import SERVER
from goperation.manager.config import manager_group

CONF = cfg.CONF

prefix = CONF[manager_group.name].redis_key_prefix


def schedule_job():
    return '%s-schedule-job-limit' % prefix


def agent_all_id():
    return '%s-%s-id-all' % (prefix, AGENT)


def async_request_key(request_id, agent_id):
    return '%s-async-%s-%d' % (prefix, request_id, agent_id)


def async_request_pattern(request_id):
    return '%s-async-%s-*' % (prefix, request_id)


def target_rpcserver(host=None, fanout=False):
    return Target(topic='%s' % SERVER, server=host,
                  fanout=SERVER if fanout else None,
                  namespace=manager_group.name)


def target_all(fanout=False):
    return Target(topic='%s.*' % AGENT, fanout=AGENT if fanout else None,
                  namespace=manager_group.name)


def target_alltype(agent_type):
    return Target(topic='%s.%s.*' % (AGENT, agent_type),
                  namespace=manager_group.name)


def target_anyone(agent_type):
    return Target(topic='%s.%s' % (AGENT, agent_type),
                  namespace=manager_group.name)


def target_server(agent_type, host, fanout=False):
    return Target(topic='%s.%s' % (AGENT, agent_type),
                  server=host, fanout=AGENT if fanout else None,
                  namespace=manager_group.name)


def target_agent(agent):
    return target_server(agent.agent_type, agent.host)


def target_agent_by_string(agent_type, host):
    return target_server(agent_type, host)


def target_endpoint(endpoint):
    return Target(fanout=endpoint, namespace=endpoint)
