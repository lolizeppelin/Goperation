# -*- coding:utf-8 -*-
import time
import webob.exc
import webob.dec
import netaddr

from simpleutil.config import cfg
from simpleutil.log import log as logging
from simpleutil.utils import uuidutils
from simpleutil.utils import jsonutils

from simpleservice import common as service_common
from simpleservice.wsgi.middleware import default_serializer
from simpleservice.wsgi.middleware import DEFAULT_CONTENT_TYPE
from simpleservice.wsgi.filter import FilterBase

from goperation.utils import get_network
from goperation.manager.config import manager_group
from goperation.manager import api
from goperation.manager.filters.config import authfilter_opts
from goperation.manager.filters.exceptions import InvalidAuthToken

LOG = logging.getLogger(__name__)

CONF = cfg.CONF


class AuthFilter(FilterBase):
    """check Auth
    """
    NAME = 'AuthFilter'

    def __init__(self, application):
        super(AuthFilter, self).__init__(application)
        CONF.register_opts(authfilter_opts, manager_group)
        self.conf = CONF[manager_group.name]
        interface, self.ipnetwork = get_network(CONF.local_ip)
        if not self.ipnetwork:
            raise RuntimeError('can not find ipaddr %s on any interface' % CONF.local_ip)
        LOG.info('Local ip %s/%s on interface %s' % (CONF.local_ip, self.ipnetwork.netmask, interface))
        self.allowed_hostname = self.conf.allowed_hostname
        self.allowed_clients = set(self.conf.allowed_trusted_ip)
        self.allowed_clients.add('127.0.0.1')
        self.allowed_clients.add(CONF.local_ip)
        # 进程中token缓存
        self.tokens = {}

    @staticmethod
    def no_auth():
        msg = 'Request Failed: HTTPUnauthorized, Please auth login first'
        body = default_serializer({'msg': msg})
        kwargs = {'body': body, 'content_type': DEFAULT_CONTENT_TYPE}
        return webob.exc.HTTPUnauthorized(**kwargs)

    def will_expire_soon(self, token):
        expire_at = self.tokens[token].get('ttl') + self.tokens[token].get('last')
        ttl = int(time.time()) - expire_at
        if ttl < 15:
            self.tokens.pop(token, None)
            raise InvalidAuthToken('Token has been expired')
        # 没有访问,tonke有效期30-60分钟,预留30秒
        if ttl < 1830:
            cache_store = api.get_cache()
            cache_store.expire(token, 3600)
            self.tokens[token]['ttl'] = 1800
            self.tokens[token]['last'] = int(time.time())

    def _fetch_token_from_cache(self, token):
        # token缓存过大, 不缓存token
        if len(self.tokens) > self.conf.token_cache_size:
            LOG.warning('Token cache is full')
            raise InvalidAuthToken('Too much token in cache')
        cache_store = api.get_cache()
        pipe = cache_store.pipeline()
        pipe.multi()
        pipe.get(token)
        pipe.ttl(token)
        results = pipe.execute()
        # 过期时间小于15s, 认为已经过期
        if results[1] < 15:
            raise InvalidAuthToken('Token has been expired')
        elif token not in self.tokens:
            self.tokens.setdefault(token, dict(ipaddr=results[0],
                                               last=int(time.time()),
                                               ttl=results[1]))
            self.will_expire_soon(token)

    def validate_token(self, req, token):
        try:
            token_info = self.tokens[token]
        except KeyError:
            return self.no_auth()
        if token_info.get('ipaddr') != req.client_addr:
            raise InvalidAuthToken('Client ipaddr not match')

    def _trusted_allowed(self, req):
        # 来源ip在允许的ip列表中
        if req.client_addr in self.allowed_clients:
            return True
        # 来源ip子网相同
        if req.client_addr in self.ipnetwork:
            return True
        return False

    def fetch_token(self, req):
        token = req.headers.get(service_common.TOKENNAME)
        if not token:
            return self.no_auth()
        if self.conf.trusted and token == self.conf.trusted:
            if not self._trusted_allowed(req):
                raise InvalidAuthToken('Trused token not from allowd ipaddr')
        if token in self.tokens:
            self.will_expire_soon(token)
        else:
            self._fetch_token_from_cache(token)
        return self.validate_token(req, token)

    def validate_host(self, req):
        if req.domain != self.allowed_hostname:
            LOG.error('remote hostname %s not match' % req.host)

    def process_request(self, req):
        try:
            path_info = req.environ['PATH_INFO']
            method = req.environ['REQUEST_METHOD']
        except KeyError:
            msg = 'Request Failed: internal server error, Can not find PATH or METHOD in environ'
            body = default_serializer({'msg': msg})
            kwargs = {'body': body, 'content_type': DEFAULT_CONTENT_TYPE}
            return webob.exc.HTTPInternalServerError(**kwargs)
        if method == 'POST' and path_info == '/goperation/auth':
            LOG.debug('AuthFilter auth')
            if not self._trusted_allowed(req):
                return webob.Response(request=req, status=403,
                                      content_type='application/json')
            ipaddr = req.headers.get('X-Real-IP')
            if not netaddr.valid_ipv4(ipaddr, netaddr.core.INET_PTON):
                return webob.Response(request=req, status=412,
                                      content_type='application/json',
                                      body=jsonutils.dumps_as_bytes(dict(message='X-Real-IP value error')))
            token = str(uuidutils.generate_uuid()).replace('-', '')
            cache_store = api.get_cache()
            if not cache_store.set(token, ipaddr, ex=3600, nx=True):
                LOG.error('Cache token fail')
                return webob.Response(request=req, status=500,
                                      content_type='application/json')
            LOG.debug('Auth success')
            self.tokens.setdefault(token, dict(last=int(time.time()), ttl=1800, ipaddr=ipaddr))
            return webob.Response(request=req, status=200,
                                  content_type='application/json',
                                  body=jsonutils.dumps_as_bytes(dict(token=token,
                                                                     name=service_common.TOKENNAME)))
        else:
            return self.fetch_token(req)


class RequestLimitFilter(FilterBase):
    """limit request times"""
