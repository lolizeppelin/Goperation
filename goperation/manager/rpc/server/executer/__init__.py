import six
import abc

from simpleutil.log import log as logging

from goperation.manager.rpc import exceptions

LOG = logging.getLogger(__name__)


@six.add_metaclass(abc.ABCMeta)
class BaseExecuter(object):
    def __init__(self, kwargs, condition):
        self.kwargs = self._kwarg_check(kwargs)
        self.condition = condition


    @abc.abstractmethod
    def _kwarg_check(self, kwargs):
        raise NotImplementedError

    @abc.abstractmethod
    def execute(self):
        raise NotImplementedError

    def run(self, *args, **kwargs):
        try:
            if self.condition:
                self.condition.check(*args, **kwargs)
            self.execute()
        except exceptions.RpcServerCtxtException as e:
            LOG.error(e.message)
            raise
        except Exception as e:
            if LOG.isEnabledFor(logging.DEBUG):
                LOG.exception('execute fail')
            else:
                LOG.error(e.message)
            raise exceptions.RpcServerCtxtException('execute fail, error type %s' % e.__class__.__name__)
