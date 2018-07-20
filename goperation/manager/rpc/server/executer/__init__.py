import six
import abc


@six.add_metaclass(abc.ABCMeta)
class BaseExecuter(object):
    def __init__(self, kwargs, condition):
        self.kwargs = self._check(kwargs)
        self.condition = condition

    @abc.abstractmethod
    def _check(self, kwargs):
        raise NotImplementedError

    @abc.abstractmethod
    def execute(self):
        raise NotImplementedError

    def pre_run(self, asyncrequest, wait_agents):
        if self.condition:
            self.condition.pre_run(asyncrequest, wait_agents)
        self.execute()

    def after_run(self, asyncrequest, wait_agents):
        if self.condition:
            self.condition.after_run(asyncrequest, wait_agents)
        self.execute()

    def post_run(self, asyncrequest, no_response_agents):
        if self.condition:
            self.condition.post_run(asyncrequest, no_response_agents)
        self.execute()
