import time
import datetime
import eventlet

from simpleutil.config import cfg
from simpleutil.log import log as logging
from simpleutil.utils import jsonutils
from simpleutil.utils import singleton

from simpleservice import loopingcall
from simpleservice.ormdb.api import model_query
from simpleservice.rpc.driver.exceptions import AMQPDestinationNotFound
from simpleservice.rpc.result import BaseRpcResult
from simpleservice.rpc.target import Target

from goperation import threadpool
from goperation.utils import safe_func_wrapper
from goperation.manager import common as manager_common
from goperation.manager.rpc.agent import base
from goperation.manager.api import get_client
from goperation.manager.api import get_session
from goperation.manager.models import Agent
from goperation.manager.models import AsyncRequest
from goperation.manager.models import ScheduleJob
from goperation.manager.models import JobStep
from goperation.manager.rpc.agent.ctxtdescriptor import CheckManagerRpcCtxt
from goperation.manager.rpc.agent.ctxtdescriptor import CheckThreadPoolRpcCtxt
from goperation.manager.rpc.agent.scheduler.taskflow import executor
from goperation.manager.rpc.agent.scheduler.taskflow import analyzer
from goperation.manager.rpc.agent.scheduler.taskflow import factory


CONF = cfg.CONF

LOG = logging.getLogger(__name__)

def safe_dumps(var):
    if var is None:
        return None
    return jsonutils.dumps_as_bytes(var)


class SchedulerLoopinTask(loopingcall.IntervalLoopinTask):
    """Report Agent online
    """
    def __init__(self, func, start, interval):
        delay = int(time.time()) - start
        if delay < 5:
            raise ValueError('Scheduler task has not enough time to start')
        self.func = func
        self._clean = None
        super(SchedulerLoopinTask, self).__init__(periodic_interval=interval,
                                                  initial_delay=delay,
                                                  stop_on_exception=True)

    def __call__(self, *args, **kwargs):
        try:
            self.func()
        except loopingcall.LoopingCallDone:
            self.func = None
            self.clean()
            raise

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
        self.timers = set()

    def post_stop(self):
        for x in self.timers:
            x.stop()
        for x in self.timers:
            try:
                x.wait()
            except Exception:
                LOG.exception("Exception occurs when wait scheduler manager timer finish")
        super(SchedulerManager, self).post_stop()

    @CheckManagerRpcCtxt
    @CheckThreadPoolRpcCtxt
    def asyncrequest(self, ctxt,
                     asyncrequest, rpc_target, rpc_method,
                     rpc_ctxt, rpc_args):
        session = get_session()
        if rpc_ctxt.get('agents') is None:
            wait_agents = set([x[0] for x in model_query(session, Agent.agent_id,
                                                         filter=Agent.status > manager_common.DELETED).all()])
        else:
            wait_agents = set(rpc_ctxt.get('agents'))
        if not asyncrequest.persist:
            rpc_ctxt.setdefaut('expire', 60)
        asyncrequest = AsyncRequest(**asyncrequest)
        asyncrequest.scheduler = self.agent_id
        target = Target(**rpc_target)
        with self.work_lock:
            rpc = get_client()
            try:
                rpc.cast(target, ctxt=rpc_ctxt, msg={'method': rpc_method, 'args': rpc_args})
            except AMQPDestinationNotFound:
                asyncrequest.resultcode = manager_common.SEND_FAIL
                asyncrequest.result = 'Async %s request send fail, AMQPDestinationNotFound' % rpc_method
                asyncrequest.status = manager_common.FINISH
                session.add(asyncrequest)
                session.flush()
                return BaseRpcResult(self.agent_id, resultcode=manager_common.RESULT_ERROR,
                                     result=asyncrequest.result)
            asyncrequest.result = 'Async request %s cast success' % rpc_method
            session.add(asyncrequest)
            session.flush()

        request_id = asyncrequest.request_id
        finishtime = asyncrequest.finishtime
        deadline = asyncrequest.deadline + 1
        persist = asyncrequest.persist
        expire = rpc_ctxt.get('expire', 60)

        def check_respone():
            wait = finishtime - int(time.time())
            if wait > 0:
                eventlet.sleep(wait)
            body = dict(agents=list(wait_agents),
                        persist=persist)
            not_overtime = 2
            while True:
                result = self.client.async_responses(request_id, body)
                not_response_agents = set(result['data'][0]['agents'])
                body['agents'] = list(not_response_agents)
                if not not_response_agents:
                    return
                if int(time.time()) > deadline:
                    not_overtime -= 1
                    if not not_overtime:
                        break
                eventlet.sleep(1)
            body.setdefault('scheduler', self.agent_id)
            body.setdefault('agent_time', int(time.time()))
            if persist:
                body.setdefault('expire', expire)
            self.client.async_overtime(request_id, body)

        threadpool.add_thread(safe_func_wrapper, check_respone, LOG)
        return BaseRpcResult(self.agent_id, resultcode=manager_common.RESULT_SUCCESS, result=asyncrequest.result)

    @CheckManagerRpcCtxt
    def scheduler(self, ctxt, job_id, jobdata, times, interval=300):
        session = get_session()
        # write job to database
        start = datetime.datetime.fromtimestamp(jobdata['start'])
        with session.begin():
            session.add(ScheduleJob(job_id=job_id,
                                    times=times,
                                    interval=interval,
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

        def run_job():
            _session = get_session()
            job = model_query(_session, ScheduleJob, filter=ScheduleJob.job_id == job_id).one()
            if job.times is not None:
                if job.times == 0:
                    raise loopingcall.LoopingCallDone
            # call taskflow run job
            factory.start_taskflow(job)
            if job.times is not None:
                job.times -= 1
            _session.commit()
            _session.close()
            if job.times is not None:
                if job.times == 0:
                    raise loopingcall.LoopingCallDone

        task = SchedulerLoopinTask(run_job, start, interval)
        periodic = loopingcall.FixedIntervalLoopingCall(task)
        periodic.start(interval=task.periodic_interval,
                       initial_delay=task.initial_delay,
                       stop_on_exception=task.stop_on_exception)
        # remove from timers when task finish
        task.clean = lambda: self.timers.discard(periodic)
        self.timers.add(periodic)
        return BaseRpcResult(result='Scheduler Job accepted', agent_id=self.agent_id)

    @CheckManagerRpcCtxt
    @CheckThreadPoolRpcCtxt
    def call_endpoint(self, endpoint, method, ctxt, **kwargs):
        func = getattr(endpoint, method)
        return func(ctxt, **kwargs)
