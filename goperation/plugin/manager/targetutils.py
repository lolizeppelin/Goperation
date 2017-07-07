from simpleutil.config import cfg
from simpleutil.utils import singleton

from glockredis import LockServiceBase

from simpleservice.rpc.target import Target

from goperation.plugin.manager.common import AGENT

from goperation.plugin.manager.config import manager_group

CONF = cfg.CONF


@singleton
class AgentLockAll(LockServiceBase):

    def __init__(self):
        self.prefix = CONF[manager_group.name].redis_key_prefix

    def _key(self):
        return '%s-lock-%s-all' % (AGENT, self.prefix)

    def _parent(self):
        return None

    def _children(self):
        return None


lock_all_agent = AgentLockAll()


class AgentLock(LockServiceBase):

    def __init__(self, agent_id):
        self.agent_id = agent_id
        self.prefix = CONF[manager_group.name].redis_key_prefix

    def _key(self):
        return '%s-lock-%s-%d' % (self.prefix, AGENT, self.agent_id)

    def _parent(self):
        return lock_all_agent

    def _children(self):
        return None


def host_online_key(agent_id):
    return '%s-online-%s-%d' % (CONF[manager_group.name].redis_key_prefix, AGENT, agent_id)


def target_all():
    return Target(topic='%s.*' % AGENT,
                  namespace=manager_group.name)


def target_alltype(agent_type):
    return Target(topic='%s.%s.*' % (AGENT, agent_type),
                  namespace=manager_group.name)


def target_anyone(agent_type):
    return Target(topic='%s.%s' % (AGENT, agent_type),
                  namespace=manager_group.name)


def target_server(agent_type, host):
    return Target(topic='%s.%s' % (AGENT, agent_type),
                  server=host,
                  namespace=manager_group.name)


def target_agent(agent):
    return target_server(agent.agent_type, agent.host)
