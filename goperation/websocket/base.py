import logging
from websockify import websocket

try:
    from http.server import SimpleHTTPRequestHandler
except:
    from SimpleHTTPServer import SimpleHTTPRequestHandler

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from simpleutil.config import cfg

from goperation.utils import suicide

CONF = cfg.CONF


class GopWebSocketServerBase(websocket.WebSocketServer):
    def __init__(self, RequestHandlerClass):
        if CONF.logfile:
            logging.basicConfig(filename=CONF.logfile)
        # suicide after 120s
        self.suicide = suicide(delay=120)
        super(GopWebSocketServerBase, self).__init__(RequestHandlerClass=RequestHandlerClass,
                                                     web=CONF.home, run_once=True,
                                                     listen_host=CONF.listen, listen_port=CONF.port,
                                                     timeout=CONF.home, cert='none_none_none',
                                                     strict_mode=CONF.strict,
                                                     tcp_keepalive=False)

    def do_handshake(self, sock, address):
        try:
            return super(GopWebSocketServerBase, self).do_handshake(sock, address)
        except Exception:
            raise self.Terminate()
