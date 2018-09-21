import six
import abc
import inspect

@six.add_metaclass(abc.ABCMeta)
class NotifyInterface(object):
    def __init__(self, notify, delay=None):
        self.delay = delay
        self.notify = notify

    @abc.abstractmethod
    def _do(self, keyword, replace=None):
        """impl do"""

    @abc.abstractmethod
    def default(self, *args, **kwargs):
        """"""

    def __getattr__(self, attrib):
        return self.default



@six.add_metaclass(abc.ABCMeta)
class GeneralNotify(object):

    def success(self):
        key = inspect.stack()[0][3]
        self._do(key)

    def fail(self):
        keyword = inspect.stack()[0][3]
        self._do(keyword)