# -*- coding:utf-8 -*-
import time

from simpleutil.utils import singleton
from simpleutil.utils import jsonutils
from simpleutil.utils import uuidutils

from simpleutil.config import cfg
from simpleutil.log import log as logging
from simpleutil.common.exceptions import InvalidArgument

from simpleservice import common as service_common

from goperation.manager import api
from goperation.manager.config import fernet_opts
from goperation.manager.utils import fernet
from goperation.manager import exceptions
from goperation.manager import common as manager_common



LOG = logging.getLogger(__name__)

CONF = cfg.CONF


CONF.register_opts(fernet_opts, CONF.find_group(manager_common.SERVER))


@singleton.singleton
class TokenProvider(object):

    AUTH_PREFIX = CONF[manager_common.NAME].redis_key_prefix + '-auth'

    def __index__(self):
        conf = CONF[manager_common.SERVER]
        try:
            self.fernet_formatter = fernet.FernetTokenFormatter(conf.fernet_key_repository,
                                                                conf.fernet_expire_days)
        except exceptions.FernetKeysNotFound:
            LOG.warning('Not supported for fernet token')
            self.fernet_formatter = None

    # ------------------  fernet token ----------------------
    def _fetch_fernet_token(self, req, token_id):
        token = self.fernet_formatter.unpack(token_id)
        return token

    # ------------------  uuid token ----------------------
    def _fetch_token_from_cache(self, token_id):
        cache_store = api.get_cache()
        # 从cache存储中获取token以及ttl
        pipe = cache_store.pipeline()
        pipe.multi()
        pipe.get(token_id)
        pipe.ttl(token_id)
        token, ttl = pipe.execute()
        # 过期时间小于15s, 认为已经过期
        if not token or ttl < 15:
            raise exceptions.TokenError('Token has been expired drop from cache')
        token = jsonutils.loads_as_bytes(token)
        return token

    def _fetch_uuid_token(self, req, token_id):
        if len(token_id) > 64:
            raise InvalidArgument('Token over size')
        # 查询缓存
        return self._fetch_token_from_cache(token_id)

    @staticmethod
    def is_fernet(req):
        return bool(req.headers.get(manager_common.FERNETHEAD, False))

    def _is_fernet(self, req):
        is_fernet = self.is_fernet(req)
        if is_fernet and not self.fernet_formatter:
            raise NotImplementedError('fernet key not init')
        return is_fernet


    @staticmethod
    def token(req):
        return req.environ[manager_common.TOKENNAME]

    # ----------------- api ----------------------
    def fetch(self, req, token_id):
        if manager_common.TOKENNAME in req.environ:
            raise exceptions.TokenError('Do not fetch token more then once')
        if self._is_fernet(req):
            token = self._fetch_fernet_token(req, token_id)
        else:
            token = self._fetch_uuid_token(req, token_id)
        req.environ[manager_common.TOKENNAME] = token
        return token

    def create(self, req, token, expire):
        if self._is_fernet(req):
            token.update({'expire': expire + int(time.time())})
            token_id = self.fernet_formatter.pack(token)
        else:
            cache_store = api.get_cache()
            token_id = '-'.join([self.AUTH_PREFIX,
                                 str(uuidutils.generate_uuid()).replace('-', '')])
            if not cache_store.set(token_id, jsonutils.dumps_as_bytes(token), ex=expire, nx=True):
                LOG.error('Cache token fail')
                raise exceptions.CacheStoneError('Set to cache store fail')
        req.environ[manager_common.TOKENNAME] = token
        return token_id

    def delete(self, req, token_id, checker=None):
        if self._is_fernet(req):
            token = self.fernet_formatter.unpack(token_id)
            if checker: checker(token)
        else:
            if not token_id.startswith(self.AUTH_PREFIX):
                raise InvalidArgument('Token id prefix error')
            cache_store = api.get_cache()
            token = cache_store.get(token_id)
            if token:
                token = jsonutils.loads_as_bytes(token)
                if checker: checker(token)
                cache_store.delete(token_id)
        return token

    def expire(self, req, token_id, expire, checker=None):
        if self._is_fernet(req):
            token = self.fernet_formatter.unpack(token_id)
            if checker: checker(token)
            expire = token.get('expire') + expire
            token.update({'expire': expire})
            token_id = self.fernet_formatter.pack(token)
        else:
            if not token_id.startswith(self.AUTH_PREFIX):
                raise InvalidArgument('Token id prefix error')
            cache_store = api.get_cache()
            token = cache_store.get(token_id)
            if not token:
                raise exceptions.TokenError('Token not exist now')
            token = jsonutils.loads_as_bytes(token)
            if checker: checker(token)
            cache_store.expire(token_id, expire)
        return token_id, token


TokenProvider = TokenProvider()