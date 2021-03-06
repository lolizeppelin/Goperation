import time
import datetime

from eventlet.semaphore import Semaphore

from simpleutil.config import cfg
from simpleutil.log import log as logging
from simpleutil.utils import jsonutils
from simpleutil.utils import singleton

from simpleservice import loopingcall
from simpleservice.ormdb.api import model_query


from goperation.manager import common as manager_common
from goperation.manager.rpc.agent import base

from goperation.manager.api import get_session
from goperation.manager.models import ScheduleJob
from goperation.manager.models import JobStep
from goperation.manager.utils.resultutils import AgentRpcResult
from goperation.manager.rpc.agent.ctxtdescriptor import CheckManagerRpcCtxt
from goperation.manager.rpc.agent.ctxtdescriptor import CheckThreadPoolRpcCtxt
from goperation.manager.rpc.agent.scheduler.taskflow import executor
from goperation.manager.rpc.agent.scheduler.taskflow import analyzer
from goperation.manager.rpc.agent.scheduler.taskflow import factory


CONF = cfg.CONF

safe_dumps = jsonutils.safe_dumps_as_bytes

LOG = logging.getLogger(__name__)


class SchedulerLoopinTask(loopingcall.IntervalLoopinTask):
    """Report Agent online
    """
    def __init__(self, job_id, func, start, interval):
        delay = int(time.time()) - start
        if delay < 5:
            raise ValueError('Scheduler task has not enough time to start')
        self.job_id = job_id
        self.func = func
        self._clean = None
        super(SchedulerLoopinTask, self).__init__(periodic_interval=interval,
                                                  initial_delay=delay,
                                                  stop_on_exception=True)

    def __call__(self, *args, **kwargs):
        try:
            self.func()
        except loopingcall.LoopingCallDone:
            self.clean()
            self.clean = None
            self.func = None
            raise
        except Exception:
            self.clean()
            self.clean = None
            self.func = None
            LOG.exception('SchedulerLoopinTask run job %d catch error' % self.job_id)
            # TODO send notify to admin
            raise loopingcall.LoopingCallDone

    @property
    def clean(self):
        if self._clean:
            return self._clean
        else:
            return lambda: None

    @clean.setter
    def clean(self, func):
        if self._clean is None:
            self._clean = func
        else:
            raise AttributeError('Do not set clean twice')


@singleton.singleton
class SchedulerManager(base.RpcAgentManager):

    agent_type = manager_common.SCHEDULER

    def __init__(self):
        base.LOG = LOG
        super(SchedulerManager, self).__init__()
        self.jobs = set()
        self.job_lock = Semaphore(1)

    def post_start(self):
        super(SchedulerManager, self).post_start()
        with self.job_lock:
            session = get_session(readonly=True)
            query = model_query(session, ScheduleJob, filter=ScheduleJob.schedule == self.agent_id)
            for job in query.all():
                if job.times is not None and job.times:
                    self.start_task(job.job_id, job.start, job.interval)

    def start_task(self, job_id, start, interval):
        with self.job_lock:
            if job_id in self.jobs:
                raise
            def task():
                session = get_session()
                query = model_query(session, ScheduleJob, filter=ScheduleJob.job_id == job_id)
                job = query.one_or_none()
                if job is None:
                    LOG.warring('Scheduler job %d has been deleted or run by this scheduler')
                    raise loopingcall.LoopingCallDone
                if job.times is not None:
                    if job.times == 0:
                        query.delete()
                        raise loopingcall.LoopingCallDone
                # call taskflow run job
                factory.start_taskflow(job)
                if job.times is not None:
                    job.times -= 1
                session.flush()
                session.close()
                if job.times is not None:
                    if job.times == 0:
                        query.delete()
                        raise loopingcall.LoopingCallDone

            task = SchedulerLoopinTask(job_id, task, start, interval)
            periodic = loopingcall.FixedIntervalLoopingCall(task)
            periodic.start(interval=task.periodic_interval,
                           initial_delay=task.initial_delay,
                           stop_on_exception=task.stop_on_exception)

            self.jobs.add(job_id)
            self.timers.add(periodic)

            # remove from timers when task finish
            def clean():
                self.timers.discard(periodic)
                self.jobs.discard(job_id)
            task.clean = clean

    @CheckManagerRpcCtxt
    def rpc_scheduler(self, ctxt, job_id, jobdata):
        if not self.is_active:
            return AgentRpcResult(self.agent_id, resultcode=manager_common.RESULT_ERROR,
                                  result='Scheduler not active now')
        session = get_session()
        # write job to database
        interval = jobdata['interval']
        start = datetime.datetime.fromtimestamp(jobdata['start'])
        with session.begin():
            session.add(ScheduleJob(job_id=job_id,
                                    times=jobdata['times'],
                                    interval=jobdata['interval'],
                                    schedule=self.agent_id,
                                    start=start,
                                    retry=jobdata['retry'],
                                    revertall=jobdata['revertall'],
                                    desc=jobdata['desc'],
                                    kwargs=safe_dumps(jobdata.get('kwargs'))))
            session.flush()
            for index, step in enumerate(jobdata['jobs']):
                executor_cls = getattr(executor, step['executor'])
                analyzer_cls = getattr(analyzer, step['executor'])
                if not executor_cls and not analyzer_cls:
                    raise NotImplementedError('executor not exist')
                # check execute and revert
                executor_cls.esure_subclass(step)
                session.add(JobStep(job_id=job_id, step=index,
                                    executor=step['executor'],
                                    kwargs=safe_dumps(step.get('kwargs', None)),
                                    execute=step.get('execute', None),
                                    revert=step.get('revert', None),
                                    method=step.get('method', None),
                                    rebind=safe_dumps(step.get('rebind', None)),
                                    provides=safe_dumps(step.get('provides', None))))
                session.flush()
        self.start_task(job_id, start, interval)
        return AgentRpcResult(result='Scheduler Job accepted', agent_id=self.agent_id)

    @CheckManagerRpcCtxt
    @CheckThreadPoolRpcCtxt
    def call_endpoint(self, endpoint, method, ctxt, **kwargs):
        func = getattr(endpoint, method)
        return func(ctxt, **kwargs)
