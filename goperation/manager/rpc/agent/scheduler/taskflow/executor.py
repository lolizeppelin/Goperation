import functools
import time
import eventlet

from simpleutil.utils import jsonutils
from simpleutil.utils import importutils
from simpleutil.utils import reflection

from simpleflow.task import FunctorTask

from goperation.taskflow import common
from goperation.manager import common as manager_common

from goperation.manager.rpc.agent.scheduler.taskflow import SchedulerTaskBase

from goperation.manager.api import get_http


def safe_load(var):
    if var is None:
        return None
    return jsonutils.loads_as_bytes(var)


class HttpRequestExecutor(SchedulerTaskBase, FunctorTask):

    ECLS = object
    RCLS = object

    @classmethod
    def builder(cls, name, jobstep, **kwargs):
        ecls = importutils.import_class(jobstep.execute)(get_http())
        method = jobstep.method
        execute = getattr(ecls, method)
        provides = safe_load(jobstep.provides)
        rebind = safe_load(jobstep.rebind)
        revert = None
        if jobstep.revert:
            revert = importutils.import_class(jobstep.revert)(ecls, method)
        return cls(name, jobstep, execute, provides, rebind, revert, **kwargs)

    def __init__(self, name, jobstep, execute, provides, rebind, revert=None):
        self.jobstep = jobstep
        super(HttpRequestExecutor, self).__init__(name=name,
                                                  execute=execute,
                                                  rebind=rebind, provides=provides)
        self._revert = revert

    def revert(self, result, *args, **kwargs):
        if self._revert:
            self._revert(result)
            self.jobstep.result = common.REVERTED
            self.jobstep.resultcode = manager_common.RESULT_UNKNOWN


class AsyncHttpRequestExecutor(HttpRequestExecutor):

    def __init__(self, name, jobstep, execute, provides, rebind, revert=None,
                 agents=True, details=False):
        self.jobstep = jobstep
        super(AsyncHttpRequestExecutor, self).__init__(name, jobstep, execute, provides, rebind, revert)
        self.agents = agents
        self.details = details

    def execute(self, *args, **kwargs):
        asyncresult = super(AsyncHttpRequestExecutor, self).execute(*args, **kwargs)['data'][0]
        finishtime = asyncresult['finishtime']
        deadline = asyncresult['deadline'] + 1
        request_id = asyncresult['request_id']
        request = functools.partial(func=getattr(reflection.get_method_self(self._execute), 'async_show'),
                                    request_id=request_id,
                                    body={'agents': self.agents, 'details': self.details})
        wait = finishtime - int(time.time())
        if wait < 0:
            wait = 0
        eventlet.sleep(wait)
        not_overtime = 2
        while True:
            aynecresult = request()['data'][0]
            if aynecresult['status'] == manager_common.FINISH:
                return aynecresult
            if int(time.time()) > deadline:
                not_overtime -= 1
                if not not_overtime:
                    raise
            eventlet.sleep(1)


class RpcCastRequestExecutor(SchedulerTaskBase, FunctorTask):
    pass


class RpcCallRequestExecutor(RpcCastRequestExecutor):
    pass
