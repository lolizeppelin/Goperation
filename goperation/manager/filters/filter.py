# -*- coding:utf-8 -*-
import netaddr
import six
import webob.dec
import webob.exc

from simpleutil.config import cfg
from simpleutil.log import log as logging
from simpleutil.common.exceptions import InvalidArgument

from simpleservice import common as service_common
from simpleservice.wsgi.filter import FilterBase
from simpleservice.wsgi.middleware import DEFAULT_CONTENT_TYPE
from simpleservice.wsgi.middleware import default_serializer

from goperation.utils import get_network
from goperation.manager import exceptions
from goperation.manager import common as manager_common
from goperation.manager.tokens import TokenProvider
from goperation.manager.config import manager_group
from goperation.manager.filters.config import authfilter_opts
from goperation.manager.filters.config import cors_opts
from goperation.manager.filters.exceptions import InvalidOriginError


LOG = logging.getLogger(__name__)

CONF = cfg.CONF


group = CONF.find_group(manager_common.SERVER)

CONF.register_opts(cors_opts, group)
CONF.register_opts(authfilter_opts, group)


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
                LOG.warning("Request header '%s' not in allow header list" % requested_header)
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
        interface, self.ipnetwork = get_network(CONF.local_ip)
        if not self.ipnetwork:
            raise RuntimeError('can not find ipaddr %s on any interface' % CONF.local_ip)
        LOG.debug('Local ip %s/%s on interface %s' % (CONF.local_ip, self.ipnetwork.netmask, interface))

        conf = CONF[manager_group.name]
        self.trusted = conf.trusted

        conf = CONF[manager_common.SERVER]
        # 使用X-Real-IP头判断来源IP, 一般在使用Nginx做前端代理的情况下用
        if conf.x_real_ip:
            IPHEAD = manager_common.XREALIP.lower()
            self._client_addr = lambda req: req.headers.get(IPHEAD)
        else:
            self._client_addr = lambda req: req.client_addr

        self.allowed_hostname = {}
        self.allowed_same_subnet = conf.allowed_same_subnet
        self.allowed_clients = set(conf.allowed_trusted_ip)
        self.allowed_clients.add('127.0.0.1')
        self.allowed_clients.add(CONF.local_ip)
        for ipaddr in self.allowed_clients:
            LOG.debug('Allowd client %s' % ipaddr)

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

    def _address_allowed(self, req):
        # 来源ip在允许的ip列表中
        ipaddr = self._client_addr(req)
        if ipaddr in self.allowed_clients:
            return True
        # 来源ip子网相同
        if self.allowed_same_subnet:
            return (netaddr.IPAddress(ipaddr) in self.ipnetwork)
        return False

    def _validate_host(self, req):
        pass
        # if req.host != self.allowed_hostname:
        #     LOG.error('remote hostname %s not match' % req.host)
        #     raise self.no_found('Hostname can not be found')

    # -------------  public token function  ------------------

    def _validate_token(self, req, token):
        # 校验token所用IP是否匹配
        if token.get(service_common.ADMINAPI, False):
            req.environ[service_common.ADMINAPI] = True
        return None

    def fetch_and_validate(self, req):
        """
        取出数据并校验
        address allowed和trusted拥有很高通过权限
        允许无token以及错误token通过
        有肯定导致依赖token的接口出错
        """
        PASS = False
        if self._address_allowed(req):
            PASS = req.environ[service_common.ADMINAPI] = True
        token_id = req.headers.get(service_common.TOKENNAME.lower())
        if not token_id:
            return None if PASS else self.no_auth()
        if len(token_id) > 256:
            return None if PASS else  self.no_auth('Token over size')
        # 可信任token,一般为用于服务组件之间的wsgi请求
        if self.trusted and token_id == self.trusted:
            req.environ[service_common.ADMINAPI] = True
            LOG.debug('Trusted token passed, address %s' % self._client_addr(req))
            PASS = True
        # 校验host
        if not PASS:
            self._validate_host(req)
        # 通过token id 获取token
        try:
            token = TokenProvider.fetch(req, token_id)
        except InvalidArgument as e:
            return None if PASS else self.client_error(e.message)
        except exceptions.TokenExpiredError as e:
            return None if PASS else self.no_auth(e.message)

        return self._validate_token(req, token)

    def process_request(self, req):
        req.environ[service_common.ADMINAPI] = False
        return self.fetch_and_validate(req)


class RequestLimitFilter(FilterBase):
    """limit request times"""
