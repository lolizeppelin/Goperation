import six
import abc

from simpleutil.log import log as logging

from goperation.manager.rpc import exceptions

LOG = logging.getLogger(__name__)


@six.add_metaclass(abc.ABCMeta)
class BaseExecuter(object):
    def __init__(self, position, kwargs, condition):
        self.kwargs = self._kwarg_check(kwargs)
        self.position = position
        self.condition = condition


    @abc.abstractmethod
    def _kwarg_check(self, kwargs):
        raise NotImplementedError

    @abc.abstractmethod
    def execute(self):
        raise NotImplementedError

    def run(self, *args, **kwargs):
        mothed = getattr(self, self.__getattribute__('%s_run' % self.position))
        if not mothed:
            raise exceptions.RpcServerCtxtException('%s mothed can not be found' % self.position)
        try:
            return mothed(*args, **kwargs)
        except exceptions.RpcServerCtxtException as e:
            LOG.error(e.message)
            raise
        except Exception as e:
            if LOG.isEnabledFor(logging.DEBUG):
                LOG.exception('%s exec fail' % self.position)
            else:
                LOG.error(e.message)
                raise exceptions.RpcServerCtxtException('%s execute fail type %s' %
                                                        (self.position, e.__class__.__name__))

    def pre_run(self, asyncrequest, wait_agents):
        if self.condition:
            self.condition.check(asyncrequest, wait_agents)
        self.execute()

    def after_run(self, asyncrequest, wait_agents):
        if self.condition:
            self.condition.check(asyncrequest, wait_agents)
        self.execute()

    def post_run(self, asyncrequest, no_response_agents):
        if self.condition:
            self.condition.check(asyncrequest, no_response_agents)
        self.execute()
