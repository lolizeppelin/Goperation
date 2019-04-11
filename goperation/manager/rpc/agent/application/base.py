import os
import contextlib
import shutil
import eventlet

from simpleutil.config import cfg
from simpleutil.log import log as logging
from simpleutil.utils import systemutils
from simpleutil.utils import attributes

from goperation.manager import common as manager_common
from goperation.manager.rpc.agent.base import RpcAgentEndpointBase
from goperation.manager.rpc.exceptions import RpcEntityError

from goperation.manager.utils.resultutils import UriResult
from goperation.manager.utils.resultutils import DirResult


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class AppEndpointBase(RpcAgentEndpointBase):
    """Endpoint base class"""

    def __init__(self, manager, name):
        super(AppEndpointBase, self).__init__(manager, name)
        self.entitys_tokens = dict()

    @property
    def apppathname(self):
        raise NotImplementedError

    @property
    def logpathname(self):
        return 'log'

    @property
    def bakpathname(self):
        return 'backup'

    def apppath(self, entity):
        return os.path.join(self.entity_home(entity), self.apppathname)

    def logpath(self, entity):
        return os.path.join(self.entity_home(entity), self.logpathname)

    def bakpath(self, entity):
        return os.path.join(self.entity_home(entity), self.bakpathname)

    def entity_user(self, entity):
        raise NotImplementedError

    def entity_group(self, entity):
        raise NotImplementedError

    def entity_home(self, entity):
        return os.path.join(self.endpoint_home, str(entity))

    def rpc_entity_token(self, ctxt, entity, token, exprie=60):
        if not attributes.is_uuid_like(token):
            LOG.error('Token error, token not uuid like')
            return None
        if entity not in self.entitys:
            LOG.error('Entity not found, add token fail')
            return None
        if entity in self.entitys_tokens:
            LOG.error('Entity last token not expried')
            return None

        def _token_overtime():
            LOG.debug('Entity token overtime')
            info = self.entitys_tokens.pop(entity, None)
            if info:
                info.clear()

        timer = eventlet.spawn_after(exprie, _token_overtime)

        self.entitys_tokens.setdefault(entity, {'token': token, 'timer': timer})

    def rpc_readlog(self, ctxt, entity, path, lines=10):
        entity = int(entity)
        lines = int(lines)
        path = str(path)
        if path.startswith('/') or '..' in path:
            return UriResult(resultcode=manager_common.RESULT_ERROR, result='path value error')
        logpath = os.path.join(self.logpath(entity), path)
        if not os.path.exists(logpath) or os.path.isdir(path):
            return UriResult(resultcode=manager_common.RESULT_ERROR,
                             result='path not exist or not a file' % path)
        try:
            uri = self.manager.readlog(logpath, self.entity_user(entity), self.entity_group(entity), lines)
        except ValueError as e:
            return UriResult(resultcode=manager_common.RESULT_ERROR,
                             result='read log of %s fail:%s' % (self.namespace, e.message))
        return UriResult(resultcode=manager_common.RESULT_SUCCESS,
                         result='get log of %s success' % self.namespace, uri=uri)

    def rpc_logs(self, ctxt, entity, path=None):
        if path:
            path = os.path.join(self.logpath(entity), path)
        else:
            path = self.logpath(entity)
        if not os.path.exists(path) or not os.path.isdir(path):
            return DirResult(resultcode=manager_common.RESULT_ERROR,
                             result='list log directory of %s.%d fail, path value error' % (self.namespace, entity))
        files = []
        dirs = []
        for _path in os.listdir(path):
            if _path.startswith('.'):
                continue
            fullpath = os.path.join(path, _path)
            if os.path.isdir(fullpath):
                dirs.append(_path)
            elif os.path.isfile(fullpath):
                files.append(_path)
        return DirResult(resultcode=manager_common.RESULT_SUCCESS,
                         result='list log directory of %s.%d success' % (self.namespace, entity),
                         dirs=dirs, files=sorted(files))

    def _entity_token(self, entity):
        info = self.entitys_tokens.pop(entity, None)
        if not info:
            return None
        timer = info.pop('timer')
        token = info.pop('token')
        timer.cancel()
        return token

    @contextlib.contextmanager
    def _prepare_entity_path(self, entity, apppath=True, logpath=True, mode=0o755):
        LOG.debug('Try prepare entity path')
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
                            os.makedirs(path, mode)
                            systemutils.chown(path, _user, _group)
                except:
                    if os.path.exists(entity_home):
                        shutil.rmtree(entity_home)
                    raise
            try:
                yield
            except:
                if os.path.exists(entity_home):
                    shutil.rmtree(entity_home)
                raise
