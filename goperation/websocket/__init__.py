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

from simpleutil.config import cfg
from simpleutil.utils.tailutils import TailWithF
from simpleutil.utils.threadgroup import ThreadGroup

CONF = cfg.CONF


class FileSendRequestHandler(websocket.WebSocketRequestHandler):
    timeout = CONF.heartbeat * 3

    def __init__(self, req, addr, server):
        websocket.WebSocketRequestHandler.__init__(self, req, addr, server)
        self.lastpush = 0
        self.lastsend = 0

    def do_GET(self):

        if '..' in self.path:
            raise ValueError('Path value is illegal')
        # 校验token
        parse = urlparse.urlparse(self.path)
        if parse.scheme != 'http':
            raise ValueError('Just for http')
        # query = parse.query
        # token = urlparse.parse_qs(query).get("token", [""]).pop()
        # if not token:
        #     hcookie = self.headers.getheader('cookie')
        #     if hcookie:
        #         cookie = Cookie.SimpleCookie()
        #         cookie.load(hcookie)
        #         if 'token' in cookie:
        #             token = cookie['token'].value

        path = self.translate_path(self.path)
        if os.path.isdir(path):
            # raise ValueError('Path is dir')
            f = self.list_directory(path)
            try:
                self.copyfile(f, self.wfile)
            finally:
                self.server.ws_connection = False
                f.close()
            return
        self.handle_websocket()
        self.close_connection = 1

    def new_websocket_client(self):

        """
        Proxy client WebSocket to normal target socket.
        """
        cqueue = []
        rlist = [self.request]
        wlist = [self.request]

        if self.server.heartbeat:
            now = time.time()
            self.heartbeat = now + self.server.heartbeat
        else:
            self.heartbeat = None

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
            self.lastpush = time.time()

        path = self.translate_path(self.path)
        tailf = TailWithF(path=path, output=output, pause=pause)
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
        if CONF.home == '/':
            raise ValueError('Home value error')
        super(FileReadWebSocketServer, self).__init__(RequestHandlerClass=RequestHandlerClass,
                                                      web=CONF.home, run_once=True,
                                                      listen_port=CONF.listen, listen_host=CONF.home,
                                                      timeout=CONF.home,
                                                      tcp_keepalive=False, strict_mode=CONF.strict)
