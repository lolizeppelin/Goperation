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
import logging

import eventlet
import six.moves.urllib.parse as urlparse
from six.moves import http_cookies as Cookie
from websockify import websocket

try:
    from http.server import SimpleHTTPRequestHandler
except:
    from SimpleHTTPServer import SimpleHTTPRequestHandler


from simpleutil.config import cfg
from simpleutil.utils.tailutils import TailWithF
from simpleutil.utils.threadgroup import ThreadGroup

CONF = cfg.CONF


class FileSendRequestHandler(websocket.WebSocketRequestHandler):


    def __init__(self, req, addr, server):
        self.timeout = CONF.heartbeat * 3
        websocket.WebSocketRequestHandler.__init__(self, req, addr, server)
        self.lastpush = 0
        self.lastsend = 0

    def do_GET(self):

        if '..' in self.path:
            raise ValueError('Path value is illegal')

        path = self.translate_path(self.path)
        if path == '/':
            raise ValueError('Home value error')
        # 校验token
        parse = urlparse.urlparse(self.path)
        # if parse.scheme != 'http':
        #     self.server.ws_connection = True
        #     raise ValueError('Just for http')
        # query = parse.query
        # token = urlparse.parse_qs(query).get("token", [""]).pop()
        # if not token:
        #     hcookie = self.headers.getheader('cookie')
        #     if hcookie:
        #         cookie = Cookie.SimpleCookie()
        #         cookie.load(hcookie)
        #         if 'token' in cookie:
        #             token = cookie['token'].value

        if not self.handle_websocket():
            if self.only_upgrade:
                self.send_error(405, "Method Not Allowed")
            else:
                if os.path.isdir(path):
                    SimpleHTTPRequestHandler.do_GET(self)
                else:
                    self.send_error(405, "Method Not Allowed")



    def new_websocket_client(self):
        self.close_connection = 1

        cqueue = []
        rlist = [self.request]
        wlist = [self.request]

        # if self.server.heartbeat:
        #     now = time.time()
        #     self.heartbeat = now + self.server.heartbeat
        # else:
        #     self.heartbeat = None

        def pause():
            if len(cqueue) > 1000:
                eventlet.sleep(0.01)
                return
            # 3秒没有文件读取,暂停0.01
            if int(time.time()) - self.lastpush > 3:
                eventlet.sleep(0.01)
                # 发送心跳
                if int(time.time()) - self.lastsend >= CONF.heartbeat:
                    self.send_ping()
                    self.lastsend = int(time.time())
                return

        def output(buf):
            cqueue.append(buf)
            self.lastpush = int(time.time())

        path = self.translate_path(self.path)
        tailf = TailWithF(path=path, output=output, pause=pause,
                          logger=logging.error)
        pool = ThreadGroup()
        tailf.start(pool)
        try:
            while True:
                # if cqueue or c_pend: wlist.append(self.request)
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
                        continue

                if excepts:
                    raise Exception("Socket exception")

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
                        raise self.CClose(closed['code'], closed['reason'])
                    return
        finally:
            tailf.stop()


class FileReadWebSocketServer(websocket.WebSocketServer):
    def __init__(self, RequestHandlerClass=FileSendRequestHandler):
        super(FileReadWebSocketServer, self).__init__(RequestHandlerClass=RequestHandlerClass,
                                                      web=CONF.home, run_once=True,
                                                      listen_host=CONF.listen, listen_port=CONF.port,
                                                      timeout=CONF.home, cert='none_none_none',
                                                      # strict_mode=CONF.strict,
                                                      tcp_keepalive=False)
