import sys
import logging
from websockify import websocket

try:
    from http.server import SimpleHTTPRequestHandler
except:
    from SimpleHTTPServer import SimpleHTTPRequestHandler

from six.moves import http_cookies as Cookie
import six.moves.urllib.parse as urlparse

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from simpleutil.config import cfg

from goperation.utils import suicide
from goperation.websocket import exceptions

CONF = cfg.CONF


class GopWebSocketServerBase(websocket.WebSocketServer):
    def __init__(self, RequestHandlerClass):
        if CONF.logfile:
            for hd in logging.root.handlers:
                logging.root.removeHandler(hd)
            logging.basicConfig(filename=CONF.logfile)
        # suicide after 120s
        self.suicide = suicide(delay=120)
        super(GopWebSocketServerBase, self).__init__(RequestHandlerClass=RequestHandlerClass,
                                                     web=CONF.home, run_once=True,
                                                     listen_host=CONF.listen, listen_port=CONF.port,
                                                     timeout=15, cert='none_none_none',
                                                     strict_mode=CONF.strict,
                                                     tcp_keepalive=False)

    def do_handshake(self, sock, address):
        try:
            return super(GopWebSocketServerBase, self).do_handshake(sock, address)
        except Exception:
            raise self.Terminate()


def fetch_token(path, headers):

    parse = urlparse.urlparse(path)
    if parse.scheme not in ('http', 'https'):
        # From a bug in urlparse in Python < 2.7.4 we cannot support
        # special schemes (cf: http://bugs.python.org/issue9374)
        if sys.version_info < (2, 7, 4):
            raise exceptions.WebSocketError("We do not support scheme '%s' under "
                                            "Python < 2.7.4, please use http or https" % parse.scheme)

    query = parse.query
    token = urlparse.parse_qs(query).get("token", [""]).pop()
    if not token:
        hcookie = headers.getheader('cookie')
        if hcookie:
            cookie = Cookie.SimpleCookie()
            cookie.load(hcookie)
            if 'token' in cookie:
                token = cookie['token'].value

    return token


