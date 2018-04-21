# -*- coding:utf-8 -*-
import six
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
from goperation.manager.filters.config import cors_opts
from goperation.manager.filters.exceptions import InvalidOriginError

LOG = logging.getLogger(__name__)

CONF = cfg.CONF


class CorsFilter(FilterBase):
    NAME = 'CORSFilter'

    simple_headers = [
        'Accept',
        'Accept-Language',
        'Content-Type',
        'Cache-Control',
        'Content-Language',
        'Expires',
        'Last-Modified',
        'Pragma'
    ]

    def __init__(self, application):
        super(CorsFilter, self).__init__(application)
        CONF.register_opts(cors_opts, CONF.find_group(manager_common.SERVER))
        self.allowed_origins = {}
        self._init_conf()

    def _init_conf(self):
        """Initialize this middleware from an oslo.config instance."""
        self._latent_configuration = {
            'allow_headers': [],
            'expose_headers': [],
            'methods': []
        }

        conf = CONF[manager_common.SERVER]

        # If the default configuration contains an allowed_origin, don't
        # forget to register that.
        self.add_origin(allowed_origin=conf.allowed_origin,
                        allow_credentials=conf.allow_credentials,
                        expose_headers=conf.expose_headers,
                        max_age=conf.max_age,
                        allow_methods=conf.allow_methods,
                        allow_headers=conf.allow_headers)

    def _get_cors_config_by_origin(self, origin):
        if origin not in self.allowed_origins:
            if '*' in self.allowed_origins:
                origin = '*'
            else:
                LOG.debug('CORS request from origin \'%s\' not permitted.'
                          % origin)
                raise InvalidOriginError(origin)
        return origin, self.allowed_origins[origin]

    def add_origin(self, allowed_origin, allow_credentials=True,
                   expose_headers=None, max_age=None, allow_methods=None,
                   allow_headers=None):
        """Add another origin to this filter.

        :param allowed_origin: Protocol, host, and port for the allowed origin.
        :param allow_credentials: Whether to permit credentials.
        :param expose_headers: A list of headers to expose.
        :param max_age: Maximum cache duration.
        :param allow_methods: List of HTTP methods to permit.
        :param allow_headers: List of HTTP headers to permit from the client.
        :return:
        """

        # NOTE(dims): Support older code that still passes in
        # a string for allowed_origin instead of a list
        if isinstance(allowed_origin, six.string_types):
            allowed_origin = [allowed_origin]

        if allowed_origin:
            for origin in allowed_origin:

                if origin in self.allowed_origins:
                    LOG.warning('Allowed origin [%s] already exists, skipping'
                                % (allowed_origin,))
                    continue

                self.allowed_origins[origin] = {
                    'allow_credentials': allow_credentials,
                    'expose_headers': expose_headers,
                    'max_age': max_age,
                    'allow_methods': allow_methods,
                    'allow_headers': allow_headers
                }

    def set_latent(self, allow_headers=None, allow_methods=None,
                   expose_headers=None):
        """Add a new latent property for this middleware.

        Latent properties are those values which a system requires for
        operation. API-specific headers, for example, may be added by an
        engineer so that they ship with the codebase, and thus do not require
        extra documentation or passing of institutional knowledge.

        :param allow_headers: HTTP headers permitted in client requests.
        :param allow_methods: HTTP methods permitted in client requests.
        :param expose_headers: HTTP Headers exposed to clients.
        """

        if allow_headers:
            if isinstance(allow_headers, list):
                self._latent_configuration['allow_headers'] = allow_headers
            else:
                raise TypeError("allow_headers must be a list or None.")

        if expose_headers:
            if isinstance(expose_headers, list):
                self._latent_configuration['expose_headers'] = expose_headers
            else:
                raise TypeError("expose_headers must be a list or None.")

        if allow_methods:
            if isinstance(allow_methods, list):
                self._latent_configuration['methods'] = allow_methods
            else:
                raise TypeError("allow_methods parameter must be a list or"
                                " None.")

    @staticmethod
    def _split_header_values(request, header_name):
        """Convert a comma-separated header value into a list of values."""
        values = []
        if header_name in request.headers:
            for value in request.headers[header_name].rsplit(','):
                value = value.strip()
                if value:
                    values.append(value)
        return values

    def _apply_cors_preflight_headers(self, request, response):
        """Handle CORS Preflight (Section 6.2)

        Given a request and a response, apply the CORS preflight headers
        appropriate for the request.
        """

        # If the response contains a 2XX code, we have to assume that the
        # underlying middleware's response content needs to be persisted.
        # Otherwise, create a new response.
        if 200 > response.status_code or response.status_code >= 300:
            response = webob.response.Response(status=webob.exc.HTTPOk.code)

        # Does the request have an origin header? (Section 6.2.1)
        if 'Origin' not in request.headers:
            return response

        # Is this origin registered? (Section 6.2.2)
        try:
            origin, cors_config = self._get_cors_config_by_origin(
                request.headers['Origin'])
        except InvalidOriginError:
            return response

        # If there's no request method, exit. (Section 6.2.3)
        if 'Access-Control-Request-Method' not in request.headers:
            LOG.debug('CORS request does not contain '
                      'Access-Control-Request-Method header.')
            return response
        request_method = request.headers['Access-Control-Request-Method']

        # Extract Request headers. If parsing fails, exit. (Section 6.2.4)
        try:
            request_headers = \
                self._split_header_values(request,
                                          'Access-Control-Request-Headers')
        except Exception:
            LOG.debug('Cannot parse request headers.')
            return response

        # Compare request method to permitted methods (Section 6.2.5)
        permitted_methods = (
            cors_config['allow_methods'] +
            self._latent_configuration['methods']
        )
        if request_method not in permitted_methods:
            LOG.debug('Request method \'%s\' not in permitted list: %s'
                      % (request_method, permitted_methods))
            return response

        # Compare request headers to permitted headers, case-insensitively.
        # (Section 6.2.6)
        permitted_headers = [header.upper() for header in
                             (cors_config['allow_headers'] +
                              self.simple_headers +
                              self._latent_configuration['allow_headers'])]
        for requested_header in request_headers:
            upper_header = requested_header.upper()
            if upper_header not in permitted_headers:
                LOG.debug('Request header \'%s\' not in permitted list: %s'
                          % (requested_header, permitted_headers))
                return response

        # Set the default origin permission headers. (Sections 6.2.7, 6.4)
        response.headers['Vary'] = 'Origin'
        response.headers['Access-Control-Allow-Origin'] = origin

        # Does this CORS configuration permit credentials? (Section 6.2.7)
        if cors_config['allow_credentials']:
            response.headers['Access-Control-Allow-Credentials'] = 'true'

        # Attach Access-Control-Max-Age if appropriate. (Section 6.2.8)
        if 'max_age' in cors_config and cors_config['max_age']:
            response.headers['Access-Control-Max-Age'] = \
                str(cors_config['max_age'])

        # Attach Access-Control-Allow-Methods. (Section 6.2.9)
        response.headers['Access-Control-Allow-Methods'] = request_method

        # Attach  Access-Control-Allow-Headers. (Section 6.2.10)
        if request_headers:
            response.headers['Access-Control-Allow-Headers'] = \
                ','.join(request_headers)

        return response

    def _apply_cors_request_headers(self, request, response):
        """Handle Basic CORS Request (Section 6.1)

        Given a request and a response, apply the CORS headers appropriate
        for the request to the response.
        """

        # Does the request have an origin header? (Section 6.1.1)
        if 'Origin' not in request.headers:
            return

        # Is this origin registered? (Section 6.1.2)
        try:
            origin, cors_config = self._get_cors_config_by_origin(
                request.headers['Origin'])
        except InvalidOriginError:
            return

        # Set the default origin permission headers. (Sections 6.1.3 & 6.4)
        response.headers['Vary'] = 'Origin'
        response.headers['Access-Control-Allow-Origin'] = origin

        # Does this CORS configuration permit credentials? (Section 6.1.3)
        if cors_config['allow_credentials']:
            response.headers['Access-Control-Allow-Credentials'] = 'true'

        # Attach the exposed headers and exit. (Section 6.1.4)
        if cors_config['expose_headers']:
            response.headers['Access-Control-Expose-Headers'] = \
                ','.join(cors_config['expose_headers'] +
                         self._latent_configuration['expose_headers'])

    def process_response(self, req, response):
        """Check for CORS headers, and decorate if necessary.
        Perform two checks. First, if an OPTIONS request was issued, let the
        application handle it, and (if necessary) decorate the response with
        preflight headers. In this case, if a 404 is thrown by the underlying
        application (i.e. if the underlying application does not handle
        OPTIONS requests, the response code is overridden.
        In the case of all other requests, regular request headers are applied.
        """

        # Sanity precheck: If we detect CORS headers provided by something in
        # in the middleware chain, assume that it knows better.
        if 'Access-Control-Allow-Origin' in response.headers:
            return response

        # Doublecheck for an OPTIONS request.
        if req.method == 'OPTIONS':
            return self._apply_cors_preflight_headers(request=req,
                                                      response=response)

        # Apply regular CORS headers.
        self._apply_cors_request_headers(request=req, response=response)

        # Finally, return the response.
        return response

    def process_request(self, req):
        return None


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
        self.allowed_same_subnet = conf.allowed_same_subnet
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

    def _address_allowed(self, req):
        # 来源ip在允许的ip列表中
        if req.client_addr in self.allowed_clients:
            return True
        # 来源ip子网相同
        if self.allowed_same_subnet and netaddr.IPAddress(req.client_addr) in self.ipnetwork:
            return True
        return False

    def fetch_and_validate_token(self, req):
        """取出并校验token"""
        token = req.headers.get(service_common.TOKENNAME.lower())
        if not token:
            return self.no_auth()
        if self.trusted and token == self.trusted:
            # 可信任token,一般为用于服务组件之间的wsgi请求
            LOG.debug('Trusted token passed, address %s', req.client_addr)
            return None
        if self._address_allowed(req):
            return None
        # token缓存部分
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
            # 获取认证的来源地址必须在可信任地址列表中
            if not self._address_allowed(req):
                LOG.warning('Auth request from illegal address %s' % req.client_addr)
                return webob.Response(request=req, status=403,
                                      content_type=DEFAULT_CONTENT_TYPE)
            ipaddr = req.headers.get('X-Real-IP'.lower())
            if not netaddr.valid_ipv4(ipaddr, netaddr.core.INET_PTON):
                return webob.Response(request=req, status=412,
                                      content_type=DEFAULT_CONTENT_TYPE,
                                      body=jsonutils.dumps_as_bytes(dict(message='X-Real-IP value error')))
            # 分配token
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
