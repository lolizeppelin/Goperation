# -*- coding:utf-8 -*-
import time
import eventlet
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
from goperation.manager import common as manager_common
from goperation.manager import api
from goperation.manager.filters.config import authfilter_opts


LOG = logging.getLogger(__name__)

CONF = cfg.CONF


class AuthFilter(FilterBase):
    """check Auth
    """
    NAME = 'AuthFilter'

    def __init__(self, application):
        super(AuthFilter, self).__init__(application)
        CONF.register_opts(authfilter_opts, CONF.find_group(manager_common.SERVER))
        interface, self.ipnetwork = get_network(CONF.local_ip)
        if not self.ipnetwork:
            raise RuntimeError('can not find ipaddr %s on any interface' % CONF.local_ip)
        LOG.info('Local ip %s/%s on interface %s' % (CONF.local_ip, self.ipnetwork.netmask, interface))

        conf = CONF[manager_group.name]
        self.trusted = conf.trusted

        conf = CONF[manager_common.SERVER]
        self.allowed_hostname = conf.allowed_hostname
        self.allowed_clients = set(conf.allowed_trusted_ip)
        self.allowed_clients.add('127.0.0.1')
        self.allowed_clients.add(CONF.local_ip)
        for ipaddr in self.allowed_clients:
            LOG.info('Allowd client %s' % ipaddr)
        # 进程token缓存最大数量
        self.token_cache_size = conf.token_cache_size

        # 进程中token缓存
        self.tokens = {}

    @staticmethod
    def no_auth(msg='Please auth login first'):
        msg = 'Request Failed: HTTPUnauthorized, %s' % msg
        body = default_serializer({'msg': msg})
        kwargs = {'body': body, 'content_type': DEFAULT_CONTENT_TYPE}
        return webob.exc.HTTPUnauthorized(**kwargs)

    @staticmethod
    def no_found(msg):
        msg = 'Request Failed: HTTPNotFound, %s' % msg
        body = default_serializer({'msg': msg})
        kwargs = {'body': body, 'content_type': DEFAULT_CONTENT_TYPE}
        return webob.exc.HTTPNotFound(**kwargs)

    @staticmethod
    def client_error(msg):
        msg = 'Request Failed: %s' % msg
        body = default_serializer({'msg': msg})
        kwargs = {'body': body, 'content_type': DEFAULT_CONTENT_TYPE}
        return webob.exc.HTTPClientError(**kwargs)

    def will_expire_soon(self, token):
        th = self.tokens[token]['th']
        expire_at = self.tokens[token].get('ttl') + self.tokens[token].get('last')
        ttl = int(time.time()) - expire_at
        if ttl < 15:
            th.cancel()
            self.tokens.pop(token, None)
            raise self.no_auth('Token has been expired')

        # 没有访问,tonke有效期30-60分钟,预留30秒
        if ttl < 1830:
            cache_store = api.get_cache()
            cache_store.expire(token, 3600)
            # io操作后有可能其他线程设置了token,再次判断
            if th is self.tokens[token]['th']:
                th.cancel()
                self.tokens[token]['ttl'] = 1800
                self.tokens[token]['last'] = int(time.time())
                self.tokens[token]['th'] = eventlet.spawn_after(3600, self.tokens.pop, token, None)

    def _fetch_token_from_cache(self, token):
        # token缓存过大, 不能缓存token,直接抛异常
        if len(self.tokens) > self.token_cache_size:
            LOG.warning('Token cache is full')
            raise self.no_auth('Too much token in cache, auth fail')
        # 从cache存储中获取token以及ttl
        cache_store = api.get_cache()
        pipe = cache_store.pipeline()
        pipe.multi()
        pipe.get(token)
        pipe.ttl(token)
        results = pipe.execute()
        # 过期时间小于15s, 认为已经过期
        if not results[0] or results[1] < 15:
            raise self.no_auth('Token has been expired')
        # io操作后有可能其他线程设置了token,再次判断
        elif token not in self.tokens:
            th = eventlet.spawn_after(results[1], self.tokens.pop, token, None)
            self.tokens.setdefault(token, dict(ipaddr=results[0],
                                               last=int(time.time()),
                                               ttl=results[1],
                                               th=th))
            self.will_expire_soon(token)

    def validate_token(self, req, token):
        try:
            token_info = self.tokens[token]
        except KeyError:
            return self.no_auth()
        if token_info.get('ipaddr') != req.client_addr:
            raise self.client_error('Client ipaddr not match')

    def _trusted_allowed(self, req):
        # 来源ip在允许的ip列表中
        if req.client_addr in self.allowed_clients:
            return True
        # 来源ip子网相同
        if netaddr.IPAddress(req.client_addr) in self.ipnetwork:
            return True
        return False

    def fetch_and_validate_token(self, req):
        """取出并校验token"""
        token = req.headers.get(service_common.TOKENNAME)
        if not token:
            return self.no_auth()
        if self.trusted and token == self.trusted:
            # 可信任token,一般为用于服务组件之间的wsgi请求
            if not self._trusted_allowed(req):
                raise self.client_error('Trused token not from allowd ipaddr')
            return None
        if token in self.tokens:
            self.will_expire_soon(token)
        else:
            self._fetch_token_from_cache(token)
        self.validate_host(req)
        return self.validate_token(req, token)

    def validate_host(self, req):
        if req.domain != self.allowed_hostname:
            LOG.error('remote hostname %s not match' % req.host)
            raise self.no_found('Hostname can not be found')

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
                                      content_type=DEFAULT_CONTENT_TYPE)
            ipaddr = req.headers.get('X-Real-IP')
            if not netaddr.valid_ipv4(ipaddr, netaddr.core.INET_PTON):
                return webob.Response(request=req, status=412,
                                      content_type=DEFAULT_CONTENT_TYPE,
                                      body=jsonutils.dumps_as_bytes(dict(message='X-Real-IP value error')))
            token = str(uuidutils.generate_uuid()).replace('-', '')
            cache_store = api.get_cache()
            if not cache_store.set(token, ipaddr, ex=3600, nx=True):
                LOG.error('Cache token fail')
                return webob.Response(request=req, status=500,
                                      content_type=DEFAULT_CONTENT_TYPE)
            LOG.debug('Auth success')
            th = eventlet.spawn_after(3600, self.tokens.pop, token, None)
            self.tokens.setdefault(token, dict(last=int(time.time()), ttl=1800, ipaddr=ipaddr,
                                               th=th))
            return webob.Response(request=req, status=200,
                                  content_type=DEFAULT_CONTENT_TYPE,
                                  body=jsonutils.dumps_as_bytes(dict(token=token,
                                                                     name=service_common.TOKENNAME)))
        else:
            return self.fetch_and_validate_token(req)


class RequestLimitFilter(FilterBase):
    """limit request times"""
