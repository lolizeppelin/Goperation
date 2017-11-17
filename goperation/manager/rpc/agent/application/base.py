import os

from simpleutil.config import cfg

from goperation.manager.rpc.agent.base import RpcAgentEndpointBase


CONF = cfg.CONF

class AppEndpointBase(RpcAgentEndpointBase):
    """"""

    def __init__(self, manager, name):
        super(AppEndpointBase, self).__init__(manager, name)
        self._home_path = os.path.join(manager.work_path, self.namespace)

    @property
    def endpoint_home(self):
        return self._home_path

    def appname(self, entity):
        raise NotImplementedError

    def entity_user(self, entity):
        raise NotImplementedError

    def entity_group(self, entity):
        raise NotImplementedError

    def entity_home(self, entity):
        return os.path.join(self.endpoint_home, 'entity_%d' % entity)

    @property
    def filemanager(self):
        return self.manager.filemanager