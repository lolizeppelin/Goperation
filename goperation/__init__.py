__version__ = '1.0.0'
VERSION = tuple(map(int, __version__.split('.')))

try:
    # call eventlet.monkey_patch first
    import simpleutil
except ImportError:
    raise

import contextlib
import psutil
from simpleutil import systemutils
from simpleutil.utils import lockutils
from simpleutil.utils.threadgroup import ThreadGroup

# public thread pool
threadpool = ThreadGroup(thread_pool_size=100)

#  Routes or wsgi
CORE_ROUTES = []
EXTEND_ROUTES = []
OPEN_ROUTES = []

# public locks
lock = lockutils.Semaphores()

@contextlib.contextmanager
def tlock(target, timeout=1.0):
    timeout = float(timeout)
    _lock = lock.get(target)
    if _lock.acquire(blocking=True, timeout=max(0.1, timeout)):
        try:
            yield
        finally:
            _lock.release()
    else:
        raise KeyError('alloc lock %s fail' % target)


if systemutils.LINUX and '4.1.0'<= psutil.__version__ <= '5.5.0':
    # patch psutil for iter connections
    import socket
    import errno
    from psutil import _pslinux


    def retrieve_iter(self, kind, pid):
        if kind not in self.tmap:
            raise ValueError("invalid %r kind argument; choose between %s"
                             % (kind, ', '.join([repr(x) for x in self.tmap])))
        self._procfs_path = _pslinux.get_procfs_path()
        inodes = self.get_proc_inodes(pid)
        if not inodes:
            # no connections for this process
            raise StopIteration
        for f, family, type_ in self.tmap[kind]:
            if family in (socket.AF_INET, socket.AF_INET6):
                ls = self.process_inet(
                    "%s/net/%s" % (self._procfs_path, f),
                    family, type_, inodes, filter_pid=pid)
            else:
                ls = self.process_unix(
                    "%s/net/%s" % (self._procfs_path, f),
                    family, inodes, filter_pid=pid)
            for fd, family, type_, laddr, raddr, status, bound_pid in ls:
                if pid:
                    conn = _pslinux._common.pconn(fd, family, type_, laddr, raddr,
                                         status)
                else:
                    conn = _pslinux._common.sconn(fd, family, type_, laddr, raddr,
                                         status, bound_pid)
                yield conn
    setattr(_pslinux.Connections, 'retrieve_iter', retrieve_iter)


    def conn_iter(self, kind='inet'):
        try:
            for conn in _pslinux._connections.retrieve_iter(kind, self.pid):
                yield conn
        except EnvironmentError as err:
            if err.errno in (errno.ENOENT, errno.ESRCH):
                raise psutil.NoSuchProcess(self.pid, self._name)
            if err.errno in (errno.EPERM, errno.EACCES):
                raise psutil.AccessDenied(self.pid, self._name)
            raise
    setattr(_pslinux.Process, 'conn_iter', conn_iter)


    def connection_iter(self, kind='inet'):
        for conn in self._proc.conn_iter(kind):
            yield conn
    setattr(psutil.Process, 'connection_iter', connection_iter)


