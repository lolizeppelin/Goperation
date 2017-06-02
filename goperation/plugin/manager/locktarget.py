from simpleutil.config import cfg

from glockredis import LockServiceBase

from goperation.plugin.manager.config import manager_group

CONF = cfg.CONF


class AgentLockAll():

    def __init__(self):
        self.prefix = CONF[manager_group.name].redis_key_prefix

    def _key(self):
        return '%s-agent-all'

    def _parent(self):
        return None

    def _children(self):
        return None

all_agent = AgentLockAll()

class AgentLock(LockServiceBase):

    def __init__(self, agent_id):
        self.agent_id = agent_id
        self.prefix = CONF[manager_group.name].redis_key_prefix

    def _key(self):
        return '%s-agent-%d' % (self.prefix, self.agent_id)

    def _parent(self):
        return all_agent

    def _children(self):
        return None
