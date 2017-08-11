from simpleutil.config import cfg

from simpleservice.rpc.target import Target

from goperation.plugin.manager.common import AGENT

from goperation.plugin.manager.config import manager_group

CONF = cfg.CONF

prefix = CONF[manager_group.name].redis_key_prefix


def agent_all_id():
    return '%s-%s-id-all' % (prefix, AGENT)


def host_online_key(agent_id):
    return '%s-online-%s-%d' % (prefix, AGENT, agent_id)


def async_request_key(request_id, agent_id):
    return '%s-async-%s-%d' % (prefix, request_id, agent_id)


def async_request_pattern(request_id):
    return '%s-async-%s-*' % (prefix, request_id)


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
