import webob.exc
import webob.dec

from simpleutil.log import log as logging

from simpleservice.wsgi.middleware import default_serializer
from simpleservice.wsgi.middleware import DEFAULT_CONTENT_TYPE
from simpleservice.wsgi.filter import FilterBase


LOG = logging.getLogger(__name__)


class AuthFilter(FilterBase):
    """check Auth
    """
    NAME = 'AuthFilter'

    def process_request(self, req):
        try:
            path_info = req.environ['PATH_INFO']
            method = req.environ['REQUEST_METHOD']
        except KeyError:
            msg = 'Request Failed: internal server error, Can not find PATH or METHOD in environ'
            body = default_serializer({'msg': msg})
            kwargs = {'body': body, 'content_type': DEFAULT_CONTENT_TYPE}
            return webob.exc.HTTPInternalServerError(**kwargs)
        if method == 'POST' and path_info == '/auth':
            LOG.debug('AuthFilter skip check url auth')
        else:
            LOG.info('AuthFilter check auth')
            # msg = 'Request Failed: HTTPUnauthorized, Please POST /auth login first'
            # body = default_serializer({'msg': msg})
            # kwargs = {'body': body, 'content_type': DEFAULT_CONTENT_TYPE}
            # return webob.exc.HTTPUnauthorized(**kwargs)


class RequestLimitFilter(FilterBase):
    """limit request times"""
