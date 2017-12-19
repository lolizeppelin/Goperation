__version__ = '1.0.0'
VERSION = tuple(map(int, __version__.split('.')))

try:
    # call eventlet.monkey_patch first
    import simpleutil
except ImportError:
    raise

import contextlib
from simpleutil.utils import lockutils
from simpleutil.utils.threadgroup import ThreadGroup

# public thread pool
threadpool = ThreadGroup(thread_pool_size=100)

#  Routes or wsgi
CORE_ROUTES = []
EXTEND_ROUTES = []

# public locks
lock = lockutils.Semaphores()

@contextlib.contextmanager
def tlock(target, timeout):
    timeout = float(timeout)
    _lock = lock.get(target)
    if _lock.acquire(blocking=True, timeout=max(0.1, timeout)):
        try:
            yield
        finally:
            _lock.release()
    else:
        raise KeyError('alloc lock %s fail' % target)

