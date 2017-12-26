import os
import contextlib
import shutil
import eventlet

from simpleutil.config import cfg
from simpleutil.utils import systemutils
from simpleutil.utils import uuidutils

from goperation.manager.rpc.agent.base import RpcAgentEndpointBase
from goperation.manager.rpc.exceptions import RpcEntityError


CONF = cfg.CONF

class AppEndpointBase(RpcAgentEndpointBase):
    """Endpoint base class"""

    def __init__(self, manager, name):
        super(AppEndpointBase, self).__init__(manager, name)
        self.entitys_tokens = dict()

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

    def rpc_entity_token(self, ctxt, entity, token, exprie=60):
        if not uuidutils.is_uuid_like(token):
            return
        if entity not in self.entitys:
            return None
        if entity in self.entitys_tokens:
            return

        def _token_overtime():
            info = self.entitys_tokens.pop(entity, None)
            if info:
                info.clear()

        timer = eventlet.spawn_after(exprie, _token_overtime)

        self.entitys_tokens.setdefault(entity, {'token': token, 'timer': timer})

    def _entity_token(self, entity):
        info = self.entitys_tokens.pop(entity, None)
        if not info:
            return None
        timer = info.pop('timer')
        token = info.pop('token')
        timer.cancel()
        return token

    @contextlib.contextmanager
    def _prepare_entity_path(self, entity, apppath=True, logpath=True):
        _user = self.entity_user(entity)
        _group = self.entity_group(entity)
        entity_home = self.entity_home(entity)
        if apppath:
            apppath = self.apppath(entity)
        if logpath:
            logpath = self.logpath(entity)

        with systemutils.prepare_user(_user, _group, entity_home):
            with systemutils.umask():
                if os.path.exists(entity_home):
                    raise RpcEntityError(self.namespace, entity, 'Entity home %s exist' % entity_home)
                try:
                    for path in (entity_home, apppath, logpath):
                        if path:
                            os.makedirs(path, 0755)
                            systemutils.chown(path, _user, _group)
                except:
                    shutil.rmtree(entity_home)
                    raise
            try:
                yield
            except:
                shutil.rmtree(entity_home)
                raise
