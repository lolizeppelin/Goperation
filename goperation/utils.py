import os
import six
import gc
import psutil
from eventlet import hubs
from netaddr import IPNetwork

from simpleutil.utils import systemutils
from simpleutil.utils import reflection
from simpleutil.log import log as logging

from simpleservice.base import SignalHandler


def safe_func_wrapper(f, logger=None):
    try:
        f()
    except Exception as e:
        if logger:
            logger.error('function %s error: %s' % (reflection.get_callable_name(f),
                                                    e.__class__.__name__))
            if hasattr(logger, 'exception'):
                logger.exception('Safe error traceback')


def suicide(delay=3):
    def _suicide():
        os._exit(1)
        # p = psutil.Process()
        # p.terminal()
        # p.terminate()
        # eventlet.sleep(3)
        # p.kill()

    hub = hubs.get_hub()
    return hub.schedule_call_global(delay, _suicide)


def nirvana(delay=1):
    """reboot self"""
    pass


if systemutils.LINUX:

    from simpleutil.utils.systemutils import posix


    def umask(umask=022):
        os.umask(umask)

    def safe_fork(user=None, group=None, umask=022):
        # Disable gc to avoid bug where gc -> file_dealloc ->
        # write to stderr -> hang.  http://bugs.python.org/issue1336
        # copy from subprocess.py
        gc_was_enabled = gc.isenabled()
        gc.disable()
        pid = os.fork()
        if pid == 0:
            # force stop eventlet loop
            def sysexit():
                os._exit(1)

            hub = hubs.get_hub()
            try:
                hub.abort(wait=False)
            except Exception:
                sysexit()

            # start new eventlet hub
            hubs.use_hub()
            hubs.get_hub()

            # set close exec for loggin
            logging.set_filehandler_close_exec()
            logging.set_syslog_handler_close_exec()

            # igonre all signal on man loop
            signal_handler = SignalHandler()
            signal_handler.clear()

            # add all signal to exit process
            signal_handler.add_handler('SIGTERM', sysexit)
            signal_handler.add_handler('SIGINT', sysexit)
            signal_handler.add_handler('SIGHUP', sysexit)
            signal_handler.add_handler('SIGALRM', sysexit)

            systemutils.drop_privileges(user, group)
            os.umask(umask)

        else:
            if gc_was_enabled:
                gc.enable()
            # force loop 100 times
            # wait sub processs stop hub
            i = 0
            while i < 100:
                i += 1
        return pid

    wait = posix.wait
else:
    def safe_fork(*args):
        raise NotImplementedError


    def umask(*args, **kwargs):
        pass

    wait = systemutils.subwait


def get_network(ipaddr):
    for interface, nets in six.iteritems(psutil.net_if_addrs()):
        for net in nets:
            if net.address == ipaddr:
                return interface, IPNetwork('%s/%s' % (ipaddr, net.netmask))
    return None, None
