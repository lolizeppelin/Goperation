# -*- coding:utf-8 -*-
from simpleutil.config import cfg

import os
import time
import select
import sys
import errno
import logging
import eventlet
import hashlib

from websockify import websocket


try:
    from http.server import SimpleHTTPRequestHandler
except:
    from SimpleHTTPServer import SimpleHTTPRequestHandler

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO


from goperation.websocket import exceptions
from goperation.websocket.base import GopWebSocketServerBase
from goperation.websocket.base import fetch_token

CONF = cfg.CONF


recver_opts = [
    cfg.StrOpt('outfile',
               required=True,
               short='o',
               help='webesocket recver output file'),
    cfg.StrOpt('md5',
               required=True,
               help='file md5 value'),
    cfg.IntOpt('size',
               required=True,
               help='file size'),
    ]


class FileRecvRequestHandler(websocket.WebSocketRequestHandler):

    def __init__(self, req, addr, server):
        self.lastrecv = 0
        if os.path.exists(CONF.outfile):
            raise ValueError('output file %s alreday exist' % CONF.outfile)
        self.timeout = CONF.heartbeat * 3
        websocket.WebSocketRequestHandler.__init__(self, req, addr, server)

    def address_string(self):
        """
        fuck gethostbyaddr!!!!!
        fuck gethostbyaddr on logging!!!
        """
        host, port = self.client_address[:2]
        return host

    def do_GET(self):

        try:
            if fetch_token(self.path, self.headers) != CONF.token:
                logging.error('Token not match')
                self.send_error(401, "Token not match")
        except exceptions.WebSocketError as e:
            self.send_error(405, e.message)

        if not self.handle_websocket():
            self.send_error(405, "Method Not Allowed")

    def new_websocket_client(self):
        size = 0
        md5 = hashlib.md5()
        self.close_connection = 1
        # cancel suicide
        logging.info('suicide cancel, start recv buffer')
        self.server.suicide.cancel()
        rlist = [self.request]
        wlist = []
        success = False
        outfile = CONF.outfile
        self.lastrecv = int(time.time())
        with open(outfile, 'wb') as f:
            while True:
                if size >= CONF.size:
                    break
                if int(time.time()) - self.lastrecv > CONF.heartbeat:
                    logging.error('Over heartbeat time')
                    break
                try:
                    ins, outs, excepts = select.select(rlist, wlist, [], 1.0)
                except (select.error, OSError):
                    exc = sys.exc_info()[1]
                    if hasattr(exc, 'errno'):
                        err = exc.errno
                    else:
                        err = exc[0]
                    if err != errno.EINTR:
                        raise
                    else:
                        eventlet.sleep(0.01)
                        continue
                if excepts:
                    raise Exception("Socket exception")

                if self.request in ins:
                    # Receive client data, decode it, and queue for target
                    bufs, closed = self.recv_frames()
                    if bufs:
                        self.lastrecv = int(time.time())
                        for buf in bufs:
                            if buf:
                                md5.update(buf)
                                f.write(buf)
                                size += len(buf)
                    if closed:
                        logging.info('Client send close')
                        break
        if size == CONF.size:
            md5 = md5.hexdigest()
            if CONF.md5 == md5:
                success = True

        if not success:
            logging.error('upload file fail, delete it')
            if os.path.exists(outfile):
                os.remove(outfile)
            logging.error('need size %d, recv %d' % (CONF.size, size))
            logging.error('need md5 %s, recv %s' % (CONF.md5, md5))


class FileRecvWebSocketServer(GopWebSocketServerBase):
    def __init__(self):
        super(FileRecvWebSocketServer, self).__init__(RequestHandlerClass=FileRecvRequestHandler)
