__version__ = '1.0.0'
VERSION = tuple(map(int, __version__.split('.')))

try:
    # call eventlet.monkey_patch first
    import simpleservice
except ImportError:
    raise

from simpleutil.utils import lockutils
from simpleutil.utils.threadgroup import ThreadGroup

lock = lockutils.Semaphores()
# public thread pool
threadpool = ThreadGroup(thread_pool_size=100)

#  Routes or wsgi
CORE_ROUTES = []
EXTEND_ROUTES = []
