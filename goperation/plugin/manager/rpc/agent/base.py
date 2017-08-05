import eventlet

from goperation.api.client.base import ManagerClient
from goperation.plugin.manager import common as manager_common
from goperation.plugin.manager import config as manager_config
from goperation.plugin.manager.rpc.agent.config import agent_group
from goperation.plugin.manager.rpc.agent.config import rpc_agent_opts
from goperation.plugin.manager.targetutils import target_server
from goperation.plugin.utils import suicide
from simpleservice.common import RESULT_ERROR
from simpleservice.common import RESULT_OVER_DEADLINE
from simpleservice.common import RESULT_SUCCESS
from simpleservice.loopingcall import IntervalLoopinTask
from simpleservice.plugin.base import ManagerBase
from simpleservice.rpc.result import BaseRpcResult
from simpleutil.config import cfg
from simpleutil.log import log as logging
from simpleutil.utils.lockutils import PriorityLock
from simpleutil.utils.sysemutils import get_partion_free_bytes
from simpleutil.utils.timeutils import realnow

CONF = cfg.CONF

LOG = logging.getLogger(__name__)

CONF.register_opts(rpc_agent_opts, agent_group)


class CheckRpcCtxt(object):
    """Rpc call need this to check ctxt
    else you shoud check deadline on ctxt
    and chekc status of Manager
    """

    def __init__(self, func=None, manager=None):
        self.func = func
        self.manager = manager

    def __get__(self, instance, owner):
        self.func = self.func.__get__(instance, owner)
        self.manager = instance
        return self

    def __call__(self, *args, **kwargs):
        ctxt = dict()
        if kwargs:
            ctxt = kwargs.get('ctxt', None)
            if ctxt is None:
                ctxt = args[0]
        deadline = ctxt.get('deadline', None)
        if self.manager.status < manager_common.HARDBUSY:
            msg = 'Rpc agent status is %d, can not do any work' % self.manager.status
            LOG.warning(msg)
            result = BaseRpcResult(ctxt, self.manager.agent_id, RESULT_ERROR, msg)
        elif deadline and int(realnow()) >= deadline:
            msg = 'Rpc receive time over deadline'
            LOG.warning(msg)
            result = BaseRpcResult(ctxt, self.manager.agent_id, RESULT_OVER_DEADLINE, msg)
        else:
            # check success
            return self.func(*args, **kwargs)
        # get reply true means a rpc call
        if ctxt.get('reply', False):
            return result
        # get a request_id means the asyncrequest need to post data to gcenter
        request_id = ctxt.get('request_id', None)
        if request_id:
            if isinstance(result, BaseRpcResult):
                result = result.to_dict()
            self.manager.client.agent_resopne(request_id, result)


class OnlinTaskReporter(IntervalLoopinTask):
    """Report Agent online
    """
    def __init__(self, manager):
        self.manager = manager
        self.with_performance = CONF[manager_common.AGENT].online_report_interval
        super(OnlinTaskReporter, self).__init__(periodic_interval=CONF[manager_common.AGENT].online_report_interval,
                                                initial_delay=0, stop_on_exception=False)

    def __call__(self, *args, **kwargs):
        self.manager.client.agent_report_online(None if not self.with_performance
                                                else self.performance_snapshot())

    def performance_snapshot(self):
        return None


class RpcAgentManager(ManagerBase):

    def __init__(self, agent_type):
        super(RpcAgentManager, self).__init__(target=target_server(agent_type, CONF.host,
                                                                   fanout=True))
        # ManagerBase.__init__(self, )
        self.rabbit_conf = CONF[manager_config.manager_rabbit_group.name]

        self.agent_type = agent_type
        self.status = manager_common.INITIALIZING
        self.endpoints = None
        self.rpcservice = None
        self._agent_id = None

        # port and port and disk space info
        conf = CONF[manager_common.AGENT]
        self.ports_range = conf.ports_range
        self.work_path = conf.work_path
        self.local_ip = conf.local_ip

        self.client = ManagerClient(host=CONF.host, local_ip=self.local_ip,
                                    agent_type=self.agent_type,
                                    wsgi_url=CONF[manager_common.AGENT].gcenter,
                                    token=CONF.trusted)

        self.work_lock = PriorityLock()
        self.work_lock.set_defalut_priority(priority=5)

        # key: port, value endpoint name
        self.allocked_ports = {}
        # left disk size
        self.partion_left_size = 0
        self._periodic_tasks = []

    def pre_start(self, external_objects):
        self.rpcservice = external_objects
        self.endpoints = external_objects.endpoints
        self.partion_left_size = get_partion_free_bytes(self.work_path)/(1024*1024)
        # get agent id of this agent
        # if agent not exist,call create
        self.client.agent_init_self(self)
        # add online report periodic tasks
        self._periodic_tasks.insert(0, OnlinTaskReporter(self))
        for endpoint in self.endpoints:

            endpoint.pre_start(self)

    def post_start(self):
        agent_info = self.client.agent_show(self.agent_id)
        status = agent_info['status']
        if status > manager_common.INITIALIZING:
            raise RuntimeError('Agent can not start, receive status is %d' % status)
        # get port allocked
        for port_info in agent_info['ports']:
            endpoint = port_info['endpoint']
            if endpoint not in self.allocked_ports:
                self.allocked_ports[endpoint] = set()
            self.allocked_ports[endpoint].add(port_info['port'])
        self.force_status(status)
        # if not self.set_status(status):
        #     raise RuntimeError('Can not change manager status after start')
        for endpoint in self.endpoints:
            endpoint.post_start()

    def post_stop(self):
        """close all endpoint here"""
        for endpoint in self.endpoints:
            endpoint.post_stop()
        self.rpcservice = None
        self.endpoints = None

    def initialize_service_hook(self):
        # check endpoint here
        for endpoint in self.endpoints:
            endpoint.initialize_service_hook()

    def full(self):
        with self.work_lock.priority(0):
            if self.status in (manager_common.HARDBUSY, manager_common.DELETED):
                return True
            if self.status > manager_common.SOFTBUSY:
                return False
        eventlet.sleep(0.5)
        with self.work_lock.priority(0):
            if self.status in (manager_common.SOFTBUSY,
                               manager_common.HARDBUSY,
                               manager_common.DELETED):
                return True
            return False

    def periodic_tasks(self):
        return self._periodic_tasks

    def set_status(self, status):
        with self.work_lock.priority(1):
            if self.status < manager_common.SOFTBUSY:
                return False
            self.status = status
        return True

    def force_status(self, status):
        with self.work_lock.priority(0):
            self.status = status

    @property
    def agent_id(self):
        if self._agent_id is None:
            raise RuntimeError('Attrib agent_id not set')
        return self._agent_id

    @agent_id.setter
    def agent_id(self, agent_id):
        with self.work_lock.priority(0):
            if self._agent_id is None:
                self._agent_id = agent_id
            else:
                if self._agent_id != agent_id:
                    raise RuntimeError('Agent init find agent_id changed')
                LOG.warning('Do not call agent_id setter more then once')

    def call_endpoint(self, endpoint, method, ctxt, args):
        super(RpcAgentManager, self).call_endpoint(endpoint, method, ctxt, args)

    @CheckRpcCtxt
    def rpc_active_agent(self, ctxt, args):
        if args.get('agent_id') != self.agent_id or args.get('agent_ipaddr') != self.local_ip:
            return BaseRpcResult(resultcode=RESULT_ERROR, result='ACTIVE agent failure, agent id or ip not match')
        status = args.get('status')
        if status not in (manager_common.ACTIVE, manager_common.UNACTIVE):
            return BaseRpcResult(resultcode=RESULT_ERROR, result='Agent change status failure, status code value error')
        with self.work_lock.priority(1):
            if self.status == status:
                return BaseRpcResult(agent_id=self.agent_id, result='Agent status not change')
            if self.status in (manager_common.ACTIVE, manager_common.UNACTIVE):
                return BaseRpcResult(agent_id=self.agent_id, result='ACTIVE or UNACTIVE agent success')
        return BaseRpcResult(resultcode=RESULT_ERROR, result='ACTIVE agent failure')

    @CheckRpcCtxt
    def rpc_status_agent(self, ctxt, args):
        pass

    @CheckRpcCtxt
    def rpc_delete_agent_precommit(self, ctxt, args):
        with self.work_lock.priority(0):
            if args['agent_id'] != self.agent_id or \
                            args['agent_type'] != self.agent_type or \
                            args['host'] != CONF.host or \
                            args['ipaddr'] != self.local_ip:
                return BaseRpcResult(resultcode=RESULT_ERROR,
                                     result='Not match this agent')
            locked_endpoints = []
            for endpont in self.endpoints:
                if not endpont.empty(lock=True):
                    while locked_endpoints:
                        locked_endpoints.pop().work_lock.release()
                    return BaseRpcResult(resultcode=RESULT_ERROR,
                                         result='Endpoint %s is not empty' % endpont.name)
                else:
                    locked_endpoints.append(endpont)
            self.status = manager_common.PERDELETE
            msg = 'Agent %s with id %d wait delete' % (CONF.host, self.agent_id)
            LOG.info(msg)
            return BaseRpcResult(resultcode=RESULT_SUCCESS, result=msg)

    def rpc_delete_agent_postcommit(self, ctxt, args):
        """postcommit without CheckRpcCtxt"""
        deadline = ctxt.get('deadline', None)
        if deadline and int(realnow()) >= deadline:
            msg = 'Rpc receive time over deadline'
            LOG.warning(msg)
            return BaseRpcResult(RESULT_OVER_DEADLINE, msg)
        with self.work_lock.priority(0):
            if args['agent_id'] != self.agent_id or \
                            args['agent_type'] != self.agent_type or \
                            args['host'] != CONF.host or \
                            args['ipaddr'] != self.local_ip:
                return BaseRpcResult(resultcode=RESULT_ERROR, result='Not match this agent')
            if self.status == manager_common.PERDELETE:
                self.status = manager_common.DELETED
                msg = 'Agent %s with id %d set status to DELETED success' % (CONF.host, self.agent_id)
                suicide(delay=3)
                return BaseRpcResult(resultcode=RESULT_SUCCESS, result=msg)
            else:
                msg = 'Agent status is not PERDELETE, status is %d' % self.status
                return BaseRpcResult(resultcode=RESULT_ERROR, result=msg)

    @CheckRpcCtxt
    def upgrade_agent(self, ctxt, args):
        pass
