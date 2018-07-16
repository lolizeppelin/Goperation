# -*- coding:utf-8 -*-
import re
import webob.exc

from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.orm.exc import MultipleResultsFound

from simpleutil.common.exceptions import InvalidArgument
from simpleutil.log import log as logging
from simpleutil.config import cfg
from simpleutil.utils import jsonutils
from simpleutil.utils import uuidutils
from simpleutil.utils import singleton
from simpleutil.utils import digestutils

from simpleservice.ormdb.api import model_query
from simpleservice.wsgi.middleware import MiddlewareContorller

from goperation.manager.config import manager_group
from goperation.manager.api import get_cache
from goperation.manager.api import get_session
from goperation.manager.utils import resultutils
from goperation.manager.exceptions import CacheStoneError

from goperation.manager.models import User

LOG = logging.getLogger(__name__)

CONF = cfg.CONF

FAULT_MAP = {
    InvalidArgument: webob.exc.HTTPClientError,
    NoResultFound: webob.exc.HTTPNotFound,
    MultipleResultsFound: webob.exc.HTTPInternalServerError,
    CacheStoneError: webob.exc.HTTPInternalServerError,
}


@singleton.singleton
class LoginReuest(MiddlewareContorller):
    NAME_REGX = re.compile('^[a-z][a-z0-9]+?$')
    AUTH_PREFIX = CONF[manager_group.name].redis_key_prefix + '-auth'

    @staticmethod
    def _name_check(username):
        if not re.match(LoginReuest.NAME_REGX, username):
            raise InvalidArgument('usernmae not illegal')
        if len(username) < 4 or len(username) > 12:
            raise InvalidArgument('usernmae over size')

    def login(self, req, username, body=None):
        body = body or {}
        password = body.get('password')
        if not password:
            raise InvalidArgument('Need password')
        self._name_check(username)
        session = get_session(readonly=True)
        query = model_query(session, User, filter=User.username == username)
        userinfo = query.one()
        if userinfo.password != digestutils.strmd5(userinfo.salt.encode('utf-8') + password):
            raise InvalidArgument('Password error')
        # 分配token
        token_id = '-'.join([self.AUTH_PREFIX,
                             str(uuidutils.generate_uuid()).replace('-', '')])
        token_data = dict(ip=req.client_addr, user=userinfo.username)
        cache_store = get_cache()
        if not cache_store.set(token_id, jsonutils.dumps_as_bytes(token_data), ex=3600, nx=True):
            LOG.error('Cache token fail')
            raise CacheStoneError('Set to cache store fail')
        LOG.debug('Auth login success')
        return resultutils.results(result='Login success',
                                   data=[dict(username=username, id=userinfo.id, token=token_id)])

    def loginout(self, req, username, body=None):
        body = body or {}
        self._name_check(username)
        token_id = str(body.get('token'))
        if token_id.startswith(self.AUTH_PREFIX):
            raise InvalidArgument('Token id prefix error')
        cache_store = get_cache()
        userinfo = cache_store.get(token_id)
        if userinfo:
            userinfo = jsonutils.loads_as_bytes(userinfo)
            if userinfo.get('user') == username:
                cache_store.delete(token_id)
            else:
                raise InvalidArgument('username not match')
        return resultutils.results(result='Login out user success')
