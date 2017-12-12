import os

from simpleutil.config import cfg
from simpleutil.utils import systemutils

from goperation.manager.rpc.agent.base import RpcAgentEndpointBase
from goperation.manager.rpc.exceptions import RpcEntityError


CONF = cfg.CONF

class AppEndpointBase(RpcAgentEndpointBase):
    """Endpoint base class"""

    def __init__(self, manager, name):
        super(AppEndpointBase, self).__init__(manager, name)

    @property
    def apppathname(self):
        raise NotImplementedError

    def apppath(self, entity):
        return os.path.join(self.entity_home(entity), self.apppathname)

    @property
    def logpathname(self):
        return NotImplementedError

    def logpath(self, entity):
        return os.path.join(self.entity_home(entity), self.logpathname)

    def entity_user(self, entity):
        raise NotImplementedError

    def entity_group(self, entity):
        raise NotImplementedError

    def entity_home(self, entity):
        return os.path.join(self.endpoint_home, str(entity))

    def _prepare_entity_path(self, entity, apppath=True, logpath=True):
        with systemutils.umask():
            entity_home = self.entity_home(entity)
            if apppath:
                apppath = self.apppath(entity)
            if logpath:
                logpath = self.logpath(entity)
            entity_user = self.entity_user(entity)
            entity_root = self.entity_group(entity)
            if os.path.exists(entity_home):
                raise RpcEntityError(self.namespace, entity, 'Entity home %s exist' % entity_home)
            for path in (entity_home, apppath, logpath):
                if path:
                    os.makedirs(path, 0755)
                    systemutils.chown(path, entity_user, entity_root)
