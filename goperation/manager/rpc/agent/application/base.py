import os

from simpleutil.config import cfg

from simpleservice.plugin.base import EndpointBase

from goperation.manager import targetutils


CONF = cfg.CONF

class AppEndpointBase(EndpointBase):
    """"""

    def __init__(self, manager, group):
        self.manager = manager
        self.group = group
        super(AppEndpointBase, self).__init__(target=targetutils.target_endpoint(self.group.name))
        self._home_path = os.path.join(manager.work_path, self.namespace)


    @property
    def filemanager(self):
        return self.manager.filemanager

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
        raise NotImplementedError
