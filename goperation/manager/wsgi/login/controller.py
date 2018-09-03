# -*- coding:utf-8 -*-
import re
import webob.exc

import eventlet
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.orm.exc import MultipleResultsFound

from simpleutil.common.exceptions import InvalidArgument
from simpleutil.log import log as logging
from simpleutil.config import cfg
from simpleutil.utils import jsonutils
from simpleutil.utils import singleton
from simpleutil.utils import digestutils

from simpleservice import common as service_common
from simpleservice.ormdb.api import model_query
from simpleservice.wsgi.middleware import MiddlewareContorller

from goperation.manager import common as manager_common
from goperation.manager.config import manager_group
from goperation.manager.tokens import TokenProvider
from goperation.manager.api import get_cache
from goperation.manager.api import get_session
from goperation.manager.utils import fernet
from goperation.manager.utils import resultutils
from goperation.manager.exceptions import CacheStoneError
from goperation.manager.exceptions import ConfigError

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
        if len(username) < 4 or len(username) > 12:
            raise InvalidArgument('usernmae over size')
        if not re.match(LoginReuest.NAME_REGX, username):
            raise InvalidArgument('usernmae not illegal')

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
        token = dict(ip=req.client_addr, user=userinfo.username)
        token.update({service_common.GOPADMIN: True})
        token_id = TokenProvider.provide(req, token, 3600)
        LOG.debug('Auth login success')
        return resultutils.results(result='Login success',
                                   data=[dict(username=username,
                                              id=userinfo.id,
                                              token=token_id,
                                              email=userinfo.email)])

    def loginout(self, req, username, token, body=None):
        body = body or {}
        self._name_check(username)

        def checker(_token):
            if not _token.get('user') == username:
                raise InvalidArgument('username not match')

        TokenProvider.delete(req, token, checker)

        return resultutils.results(result='Login out user success')

    def expire(self, req, username, token, body=None):

        def checker(_token):
            if not _token.get('user') == username:
                raise InvalidArgument('username not match')
            session = get_session(readonly=True)
            query = model_query(session, User, filter=User.username == _token.get('user'))
            query.one()

        token_id, token = TokenProvider.expire(req, token, checker)

        return resultutils.results(result='Expire token success',
                                   data=[dict(token=token_id)])
