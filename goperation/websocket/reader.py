# -*- coding:utf-8 -*-
# Copyright (c) 2012 OpenStack Foundation
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
import os
import time
import select
import sys
import errno
import cgi
import logging

import eventlet
import six.moves.urllib.parse as urlparse
from six.moves import http_cookies as Cookie
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
from simpleutil.utils import systemutils
from simpleutil.utils import jsonutils
from simpleutil.utils.tailutils import TailWithF
from simpleutil.utils.threadgroup import ThreadGroup

from goperation.utils import suicide

from goperation.websocket.base import GopWebSocketServerBase

CONF = cfg.CONF

reader_opts = [
    cfg.IntOpt('lines',
               short='n',
               min=1,
               help='output the last n lines, instead of the last 10'),
    ]


class FileSendRequestHandler(websocket.WebSocketRequestHandler):


    def __init__(self, req, addr, server):
        self.lastsend = 0
        self.timeout = CONF.heartbeat * 3
        # suicide after 300s
        self.suicide = suicide(delay=30)
        websocket.WebSocketRequestHandler.__init__(self, req, addr, server)

    def do_GET(self):

        if '..' in self.path:
            raise ValueError('Path value is illegal')

        path = self.translate_path(self.path)
        if path == '/':
            raise ValueError('Home value error')
        # 校验token
        token = object()
        hcookie = self.headers.getheader('cookie')
        if hcookie:
            cookie = Cookie.SimpleCookie()
            cookie.load(hcookie)
            if 'token' in cookie:
                token = cookie['token'].value
        if token != CONF.token:
            logging.error('token error')
            # self.send_error(404, "Token not match")


        if not self.handle_websocket():
            if self.only_upgrade:
                self.send_error(405, "Method Not Allowed")
            else:
                if os.path.isdir(path):
                    if not self.path.endswith('/'):
                        # redirect browser - doing basically what apache does
                        self.send_response(301)
                        self.send_header("Location", self.path + "/")
                        self.end_headers()
                        return None
                    try:
                        filelist = os.listdir(path)
                    except os.error:
                        self.send_error(404, "No permission to list directory")
                        return None
                    _filelist = []
                    filelist.sort(key=lambda a: a.lower())
                    f = StringIO()
                    for name in filelist:
                        fullname = os.path.join(path, name)
                        displayname = name
                        if os.path.isdir(fullname):
                            displayname = name + "/"
                        if os.path.islink(fullname):
                            displayname = name + "@"
                        _filelist.append(cgi.escape(displayname))
                    buf = jsonutils.dumps_as_bytes(_filelist)
                    self.send_response(200)
                    self.send_header("Content-type", "application/json; charset=%s" % systemutils.SYSENCODE)
                    self.send_header("Content-Length", len(buf))
                    self.end_headers()
                    self.wfile.write(buf)
                    return f.close()
                else:
                    self.send_error(405, "Method Not Allowed")

    def new_websocket_client(self):
        self.close_connection = 1
        # cancel suicide
        logging.info('Suicide cancel')
        self.suicide.cancel()

        cqueue = []
        rlist = [self.request]
        wlist = [self.request]

        def output(buf):
            cqueue.append(buf)
            self.lastsend = int(time.time())

        path = self.translate_path(self.path)
        tailf = TailWithF(path=path, output=output,
                          logger=logging.error, rows=CONF.lines)
        pool = ThreadGroup()
        tailf.start(pool)
        try:
            while True:
                if int(time.time()) - self.lastsend > CONF.heartbeat:
                    self.send_ping()
                    bufs, closed = self.recv_frames()
                    if closed:
                        logging.info('Send ping find close')
                        return
                    if bufs:
                        logging.info('Send ping but recv buffer')
                        return
                    self.lastsend = int(time.time())
                if tailf.stoped:
                    logging.warning('Tail intance is closed')
                    return
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

                if not cqueue:
                    eventlet.sleep(0.01)

                if cqueue and self.request in outs:
                    # Send queued target data to the client
                    self.send_frames(cqueue)
                    self.lastsend = int(time.time())
                    cqueue = []

                if self.request in ins:
                    # Receive client data, decode it, and queue for target
                    bufs, closed = self.recv_frames()
                    if closed:
                        logging.info('Client send close')
                        return
                    logging.info('Client send to server')
                    return
        finally:
            tailf.stop()


class FileReadWebSocketServer(GopWebSocketServerBase):
    def __init__(self):
        super(FileReadWebSocketServer, self).__init__(RequestHandlerClass=FileSendRequestHandler)
