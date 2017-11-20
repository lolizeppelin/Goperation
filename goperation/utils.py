import os
import gc
import psutil
import eventlet
from eventlet import hubs

from simpleutil.utils import systemutils
from simpleutil.log import log as logging

from simpleservice.base import SignalHandler


def safe_func_wrapper(f, logger=None):
    try:
        f()
    except Exception as e:
        if logger:
            logger.error('Safe wrapper cache error: %s' % e.__class__.__name__)
            logger.debug(str(e))


def suicide(delay=3):
    def _suicide():
        p = psutil.Process()
        p.terminal()
        eventlet.sleep(3)
        p.kill()
    hub = hubs.get_hub()
    hub.schedule_call_global(delay, _suicide)


def nirvana(delay=1):
    """reboot self"""
    pass


if systemutils.LINUX:
    from simpleutil.utils.systemutils.posix import linux

    def safe_fork(user=None, group=None):
        # Disable gc to avoid bug where gc -> file_dealloc ->
        # write to stderr -> hang.  http://bugs.python.org/issue1336
        # copy from subprocess.py
        gc_was_enabled = gc.isenabled()
        gc.disable()
        try:
            pid = os.fork()
        except:
            if gc_was_enabled:
                gc.enable()
            raise
        if pid == 0:
            linux.drop_privileges(group, user)
            os.umask(002)
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
            # start new eventlet hub
            hubs.use_hub()
            hubs.get_hub()

        else:
            if gc_was_enabled:
                gc.enable()
        return pid

    wait = linux.wait
else:
    def safe_fork(*args):
        raise NotImplementedError

    wait = systemutils.subwait
