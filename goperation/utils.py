import os
import gc
import psutil
import eventlet
from eventlet import hubs

from simpleutil.utils import systemutils
from simpleutil.log import log as logging

from simpleservice.base import SignalHandler

INTERVAL = 0.01


class ExitBySIG(Exception):
    """"""


class UnExceptExit(Exception):
    """"""


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
    import signal
    import errno

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
            if group:
                linux.setgid(group)
            if user:
                linux.setuid(user)
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

    def wait(pid, timeout=None):
        used_time = 0.0
        timeout = float(timeout) if timeout else None
        while True:
            try:
                # same as eventlet.green.os.wait
                _pid, status = os.waitpid(pid, os.WNOHANG)
                if not _pid:
                    if timeout and used_time > timeout:
                        os.kill(pid, signal.SIGTERM)
                        _pid, status = os.waitpid(pid, os.WNOHANG)
                        if not _pid:
                            os.kill(pid, signal.SIGKILL)
                        os.waitpid(pid, 0)
                        raise ExitBySIG('sub process terminated or killed')
                    eventlet.sleep(INTERVAL)
                    used_time += INTERVAL
                    continue
                else:
                    if not os.WIFSIGNALED(status):
                        code = os.WEXITSTATUS(status)
                        if code != 0:
                            raise UnExceptExit('sup process exit code %d' % code)
                        break
                    else:
                        raise ExitBySIG('sub process exit with by signal, maybe timeout')
            except OSError as exc:
                if exc.errno not in (errno.EINTR, errno.ECHILD):
                    raise OSError('waitpid get errno %d' % exc.errno)
                continue
else:

    def safe_fork(*args):
        raise NotImplementedError

    def wait(sub, timeout=None):
        used_time = 0.0
        timeout = float(timeout) if timeout else None
        while True:
            try:
                # same as eventlet.green.os.wait
                if sub.poll() is None:
                    if timeout and used_time > timeout:
                        sub.terminate()
                        if sub.poll() is None:
                            sub.kill()
                        sub.wait()
                        raise ExitBySIG('sub process exit with by signal, maybe timeout')
                    eventlet.sleep(INTERVAL)
                    used_time += INTERVAL
                    continue
                else:
                    code = sub.wait()
                    if code != 0:
                        raise UnExceptExit('sup process exit code %d' % code)
                    break
            except OSError as exc:
                if exc.errno not in (errno.EINTR, errno.ECHILD):
                    raise OSError('waitpid get errorno %d' % exc.errno)
                continue
