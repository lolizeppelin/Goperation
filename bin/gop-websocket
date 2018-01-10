#!/usr/bin/python
import logging

from simpleutil.config import cfg

from goperation.websocket.config import websocket_opts
from goperation.websocket import FileReadWebSocketServer


def main():
    logging.basicConfig(level=logging.WARN)
    conf = cfg.ConfigOpts()
    conf.register_cli_opts(websocket_opts)
    conf()
    websocket_server = FileReadWebSocketServer()
    websocket_server.start_server()


if __name__ == '__main__':
    main()
