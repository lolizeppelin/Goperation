import sys
import re
import os
import psutil
import eventlet
from eventlet import hubs
import greenlet

from simpleutil.log import log as logging

from simpleservice.base import SignalHandler

from goperation.plugin import common as plugin_common

mswindows = (sys.platform == "win32")


def validate_endpoint(value):
    if not isinstance(value, basestring):
        raise ValueError('Entpoint name is not basestring')
    if len(value) > plugin_common.MAX_HOST_NAME_SIZE:
        raise ValueError('Entpoint name over size')
    if not re.match(plugin_common.regx_endpoint, value):
        raise ValueError('Entpoint name %s not match regx' % value)
    return value.lower()


def validate_endpoints(value):
    if isinstance(value, basestring):
        return [validate_endpoint(value)]
    if isinstance(value, (list, tuple)):
        endpoints = set()
        for endpoint in value:
            endpoints.add(validate_endpoint(endpoint))
        return list(endpoints)
    raise ValueError('Entpoint list type error')


def suicide(delay=0):
    def _suicide():
        p = psutil.Process()
        p.terminal()
        eventlet.sleep(3)
        p.kill()
    hub = hubs.get_hub()
    g = greenlet.greenlet(_suicide, parent=hub.greenlet)
    hub.schedule_call_global(delay, g.switch)

if mswindows:

    def safe_fork():
        raise NotImplementedError

else:

    def safe_fork():
        pid = os.fork()
        if pid == 0:
            # set close exec for loggin
            logging.set_filehandler_close_exec()
            logging.set_syslog_handler_close_exec()
            # igonre all signal on man loop
            signal_handler = SignalHandler()
            signal_handler.clear()

            def sysexit():
                os._exit(1)

            # add all signal to exit process
            signal_handler.add_handler('SIGTERM', sysexit)
            signal_handler.add_handler('SIGINT', sysexit)
            signal_handler.add_handler('SIGHUP', sysexit)
            signal_handler.add_handler('SIGALRM', sysexit)
            hub = hubs.get_hub()
            # force stop eventlet loop
            try:
                hub.abort(wait=False)
            except:
                sysexit()
        return pid

