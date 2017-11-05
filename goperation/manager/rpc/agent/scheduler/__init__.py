import time
import datetime
import eventlet

from simpleutil.config import cfg
from simpleutil.log import log as logging
from simpleutil.utils import jsonutils
from simpleutil.utils import singleton
from simpleutil.utils import importutils

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
from goperation.manager.models import AgentRespone
from goperation.manager.models import AsyncRequest
from goperation.manager.models import ScheduleJob
from goperation.manager.models import JobStep
from goperation.manager.rpc.agent.ctxtdescriptor import CheckManagerRpcCtxt
from goperation.manager.rpc.agent.ctxtdescriptor import CheckThreadPoolRpcCtxt


CONF = cfg.CONF

LOG = logging.getLogger(__name__)


@singleton.singleton
class SchedulerManager(base.RpcAgentManager):

    agent_type = manager_common.SCHEDULER

    def __init__(self):
        base.LOG = LOG
        super(SchedulerManager, self).__init__()
        self.timers = []

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
        asyncrequest = AsyncRequest(**asyncrequest)
        asyncrequest.scheduler = self.agent_id
        target = Target(**rpc_target)
        with self.work_lock:
            rpc = get_client()
            try:
                rpc.cast(target, ctxt=rpc_args, msg={'method': rpc_method, 'args': rpc_args})
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

        def check_respone():
            now = int(time.time())
            wait_time = asyncrequest.finishtime - now
            if wait_time > 0:
                eventlet.sleep(wait_time)
            query = model_query(get_session(readonly=True),
                                AgentRespone.agent_id,
                                filter=AgentRespone.request_id == asyncrequest.request_id)
            finish_agents = set()
            while True:
                for row in query.all():
                    finish_agents.add(row[0])
                if finish_agents == wait_agents:
                    return
                if int(time.time()) > asyncrequest.deadline:
                    agents_over_deadline = wait_agents - finish_agents
                    self.client.scheduler_overtime_respone(asyncrequest.request_id,
                                                           {'agents': agents_over_deadline})
                    if finish_agents - wait_agents:
                        LOG.warning('Finished async request agent more then agents in ctxt')
                        LOG.debug('Agent %s is finished, but not in ctxt' % str(finish_agents - wait_agents))
                    break
                finish_agents.clear()
                eventlet.sleep(0.25)
            # some agent not respon
            body = dict(agents=list(wait_agents - finish_agents),
                        persist=asyncrequest.persist,
                        agent_time=int(time.time()),
                        scheduler=self.agent_id)
            self.client.scheduler_overtime_respone(asyncrequest.request_id, body)

        threadpool.add_thread(safe_func_wrapper, check_respone, LOG)
        return BaseRpcResult(self.agent_id, resultcode=manager_common.RESULT_SUCCESS, result=asyncrequest.result)

    @CheckManagerRpcCtxt
    @CheckThreadPoolRpcCtxt
    def scheduler(self, ctxt, job_id, jobdata, dispose=True):
        session = get_session()
        start=datetime.datetime.fromtimestamp(jobdata['start']),
        end=datetime.datetime.fromtimestamp(jobdata['end']),
        deadline=datetime.datetime.fromtimestamp(jobdata['deadline'])
        with session.begin():
            session.add(ScheduleJob(job_id=job_id,
                                    schedule=self.agent_id,
                                    start=start,
                                    end=end,
                                    deadline=deadline))
            session.flush()
            for index, step in enumerate(jobdata['jobs']):
                if step.get('revert'):
                    rcls=step['revert']['cls']
                    rmethod=step['revert']['method']
                    rargs=jsonutils.dumps_as_bytes(step['revert']['args']) if step['revert']['args'] else None
                    cls = importutils.import_class(rcls)
                    if not hasattr(cls, rmethod):
                        raise NotImplementedError('%s no method %s' % (rcls, rmethod))
                else:
                    rcls=None
                    rmethod=None
                    rargs=None
                session.add(JobStep(job_id=job_id, step=index,
                            ecls=step['execute']['cls'],
                            emethod=step['execute']['method'],
                            eargs=jsonutils.dumps_as_bytes(step['execute']['args']),
                            rcls=rcls, rmethod=rmethod, rargs=rargs))
                session.flush()
        return BaseRpcResult(result='Scheduler Job accepted', agent_id=self.agent_id)

    @CheckManagerRpcCtxt
    @CheckThreadPoolRpcCtxt
    def call_endpoint(self, endpoint, method, ctxt, **kwargs):
        func = getattr(endpoint, method)
        return func(ctxt, **kwargs)
