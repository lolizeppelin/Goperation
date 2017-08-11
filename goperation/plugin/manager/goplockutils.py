from simpleutil.config import cfg
from simpleutil.utils import singleton

from glockredis import LockServiceBase

from goperation.plugin.manager.common import AGENT
from goperation.plugin.manager.config import manager_group

CONF = cfg.CONF

prefix = CONF[manager_group.name].redis_key_prefix


@singleton
class AgentLockAll(LockServiceBase):

    def _key(self):
        return '%s-lock-%s' % (AGENT, prefix)

    def _parent(self):
        return None


lock_all_agent = AgentLockAll()


class AgentLock(LockServiceBase):

    def __init__(self, agent_id):
        self.agent_id = agent_id

    def _key(self):
        return '%s-%d' % (lock_all_agent, self.agent_id)

    def _parent(self):
        return lock_all_agent
