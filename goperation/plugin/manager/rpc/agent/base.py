import eventlet
import random

from simpleutil.config import cfg
from simpleutil.log import log as logging
from simpleutil.utils import importutils
from simpleutil.utils import jsonutils
from simpleutil.utils.attributes import validators
from simpleutil.utils.lockutils import PriorityLock
from simpleutil.utils.sysemutils import get_partion_free_bytes

from simpleservice.loopingcall import IntervalLoopinTask
from simpleservice.plugin.base import ManagerBase
from simpleservice.rpc.result import BaseRpcResult
from simpleservice.rpc.config import rpc_server_opts

from goperation.api.client.base import ManagerClient
from goperation.plugin.manager import common as manager_common
from goperation.plugin.manager import config as manager_config
from goperation.plugin.manager.rpc.agent.config import agent_group
from goperation.plugin.manager.rpc.agent.config import rpc_agent_opts
from goperation.plugin.manager.rpc.ctxtdescriptor import CheckEndpointRpcCtxt
from goperation.plugin.manager.rpc.ctxtdescriptor import CheckManagerRpcCtxt
from goperation.plugin.manager.wsgi.targetutils import target_server
from goperation.plugin.utils import suicide


CONF = cfg.CONF

LOG = logging.getLogger(__name__)

CONF.register_opts(rpc_agent_opts, agent_group)


class OnlinTaskReporter(IntervalLoopinTask):
    """Report Agent online
    """
    def __init__(self, manager):
        self.manager = manager
        self.with_performance = CONF[manager_common.AGENT].report_performance
        interval = CONF[manager_common.AGENT].online_report_interval
        super(OnlinTaskReporter, self).__init__(periodic_interval=interval,
                                                initial_delay=interval+random.randint(-30,30),
                                                stop_on_exception=False)

    def __call__(self, *args, **kwargs):
        self.manager.client.agent_report_online(self.performance_snapshot())

    def performance_snapshot(self):
        if not self.with_performance:
            return None
        # TODO do a system performance snapshot with psutil
        return None


class RpcAgentManager(ManagerBase):

    def __init__(self, **kwargs):
        super(RpcAgentManager, self).__init__(target=target_server(self.agent_type, CONF.host,
                                                                   fanout=True))
        self.rabbit_conf = CONF[manager_config.manager_rabbit_group.name]
        CONF.register_opts(rpc_server_opts, manager_config.manager_rabbit_group)

        self.status = manager_common.INITIALIZING

        self.rpcservice = None
        self._agent_id = None
        self.endpoints = set()
        # append endpoint config
        if CONF.endpoints:
            # endpoint class must be singleton
            for endpoint in CONF.endpoints:
                endpoint_class = importutils.import_class(endpoint)
                endpoint_kwargs = kwargs.get(endpoint_class.__name__.lower(), {})
                endpoint_kwargs.update({'agent_type': self.agent_type})
                self.endpoints.add(endpoint_class(**endpoint_kwargs))
        # port and port and disk space info
        conf = CONF[manager_common.AGENT]
        self.ports_range = validators['type:ports_range_list'](conf.ports_range) \
            if conf.ports_range else []
        self.work_path = conf.work_path
        self.local_ip = conf.local_ip

        # TODO file finder or manager
        self.files = None
        self.client = ManagerClient(host=CONF.host, local_ip=self.local_ip,
                                    agent_type=self.agent_type,
                                    wsgi_url=CONF[manager_common.AGENT].gcenter,
                                    wsgi_port=CONF[manager_common.AGENT].gcenter_port,
                                    token=CONF.trusted)

        self._periodic_tasks = []
        # key: port, value endpoint name
        self.allocked_ports = {}
        # left ports
        self.left_ports = set()
        for p_range in self.ports_range:
            up, down = map(int, p_range.split('-'))
            for port in xrange(up, down):
                self.left_ports.add(port)

        self.work_lock = PriorityLock()
        self.work_lock.set_defalut_priority(priority=5)

    def pre_start(self, external_objects):
        self.rpcservice = external_objects
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
        if status <= manager_common.SOFTBUSY:
            raise RuntimeError('Agent can not start, receive status is %d' % status)
        # get port allocked
        for port_info in agent_info['ports']:
            self.frozen_port(port_info['endpoint'], port_info['port'])
        remote_ports_range = jsonutils.loads(agent_info['ports_range'])
        if  remote_ports_range != self.ports_range:
            LOG.warning('Agent ports range has been changed at remote database')
            body = {'ports_range': jsonutils.dump_as_bytes(self.ports_range)}
            # call agent change ports_range
            self.client.agent_edit(agent_id=self.agent_id, body=body)
        # agent set status at this moment
        # before status set, all rpc will requeue by RPCDispatcher
        # so function agent_show in wsgi server do not need agent lock
        self.force_status(status)
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
            if self.status == manager_common.PERDELETE:
                return False
            if self.status > manager_common.SOFTBUSY:
                return False
            if manager_common < manager_common.SOFTBUSY:
                return True
        eventlet.sleep(0.5)
        # soft busy can wait 0.5 to recheck
        with self.work_lock.priority(0):
            if self.status <= manager_common.SOFTBUSY:
                return True
            return False

    def periodic_tasks(self):
        return self._periodic_tasks

    def frozen_port(self, endpoint, ports=None):
        with self.work_lock.priority(3):
            if endpoint not in self.allocked_ports:
                self.allocked_ports[endpoint] = set()
            allocked_port = set()
            if ports is None:
                ports = [ports]
            for port in ports:
                try:
                    if port is not None:
                        self.left_ports.remove(port)
                    else:
                        port = self.left_ports.pop()
                except KeyError:
                    LOG.error('Agent allocked port fail')
                    self.free_ports(allocked_port)
                    raise
                self.allocked_ports[endpoint].add(port)
                allocked_port.add(port)
            return allocked_port

    def free_ports(self, ports):
        _ports = set()
        with self.work_lock.priority(2):
            if isinstance(ports, (int, long)):
                _ports.add(ports)
            else:
                _ports = set(ports)
        for allocked_ports in self.allocked_ports.values():
            intersection_ports = allocked_ports & _ports
            for port in intersection_ports:
                allocked_ports.remove(port)
                _ports.remove(port)
                self.left_ports.add(port)
        if _ports:
            LOG.error('%d port can not be found after free ports' % len(_ports))

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
    def is_active(self):
        with self.work_lock:
            if self.status >= manager_common.ACTIVE:
                return True
        return False

    @property
    def partion_left_size(self):
        return get_partion_free_bytes(self.work_path)/(1024*1024)

    @property
    def agent_id(self):
        if self._agent_id is None:
            raise RuntimeError('Attrib agent_id not set')
        return self._agent_id

    @agent_id.setter
    def agent_id(self, agent_id):
        if not isinstance(agent_id, int):
            raise RuntimeError('Agent is not value type error, not int')
        with self.work_lock.priority(0):
            if self._agent_id is None:
                self._agent_id = agent_id
            else:
                if self._agent_id != agent_id:
                    raise RuntimeError('Agent init find agent_id changed')
                LOG.warning('Do not call agent_id setter more then once')

    @CheckManagerRpcCtxt
    @CheckEndpointRpcCtxt
    def call_endpoint(self, endpoint, method, ctxt, **kwargs):
        return ManagerBase.call_endpoint(self, endpoint, method, ctxt, **kwargs)

    @CheckManagerRpcCtxt
    def rpc_active_agent(self, ctxt, **kwargs):
        if kwargs.get('agent_id') != self.agent_id or kwargs.get('agent_ipaddr') != self.local_ip:
            return BaseRpcResult(self.agent_id, ctxt,
                                 resultcode=manager_common.RESULT_ERROR,
                                 result='ACTIVE agent failure, agent id or ip not match')
        status = kwargs.get('status')
        if not isinstance(status, (int, long)) or status <= manager_common.SOFTBUSY:
            return BaseRpcResult(self.agent_id, ctxt,
                                 resultcode=manager_common.RESULT_ERROR,
                                 result='Agent change status failure, status code value error')
        if not self.set_status(status):
            return BaseRpcResult(self.agent_id, ctxt,
                                 resultcode=manager_common.RESULT_ERROR,
                                 result='ACTIVE agent failure, can not set stauts now')
        return BaseRpcResult(self.agent_id, ctxt,
                             resultcode=manager_common.RESULT_SUCCESS, result='ACTIVE agent success')

    @CheckManagerRpcCtxt
    def rpc_status_agent(self, ctxt, **kwargs):
        return BaseRpcResult(self.agent_id, ctxt,
                             resultcode=manager_common.RESULT_SUCCESS,
                             result='Get status from %s success' % self.local_ip,
                             # TODO more info of endpoint
                             details=[dict(name=endpoint.name, entiys=endpoint.entiys)
                                      for endpoint in self.endpoints])

    @CheckManagerRpcCtxt
    def rpc_delete_agent_precommit(self, ctxt, **kwargs):
        with self.work_lock.priority(0):
            if self.status <= manager_common.SOFTBUSY:
                return BaseRpcResult(self.agent_id, ctxt,
                                     resultcode=manager_common.RESULT_ERROR,
                                     result='Can not change status now')
            if kwargs['agent_id'] != self.agent_id \
                    or kwargs['agent_type'] != self.agent_type \
                    or kwargs['host'] != CONF.host \
                    or kwargs['ipaddr'] != self.local_ip:
                return BaseRpcResult(self.agent_id, ctxt,
                                     resultcode=manager_common.RESULT_ERROR,
                                     result='Not match this agent')
            for endpont in self.endpoints:
                if endpont.entiys:
                    return BaseRpcResult(self.agent_id, ctxt,
                                         resultcode=manager_common.RESULT_ERROR,
                                         result='Endpoint %s is not empty' % endpont.name)
            self.status = manager_common.PERDELETE
            msg = 'Agent %s with id %d wait delete' % (CONF.host, self.agent_id)
            LOG.info(msg)
            return BaseRpcResult(self.agent_id, ctxt,
                                 resultcode=manager_common.RESULT_SUCCESS, result=msg)

    @CheckManagerRpcCtxt
    def rpc_delete_agent_postcommit(self, ctxt, **kwargs):
        with self.work_lock.priority(0):
            if kwargs['agent_id'] != self.agent_id or \
                            kwargs['agent_type'] != self.agent_type or \
                            kwargs['host'] != CONF.host or \
                            kwargs['ipaddr'] != self.local_ip:
                return BaseRpcResult(self.agent_id, ctxt,
                                     resultcode=manager_common.RESULT_ERROR, result='Not match this agent')
            if self.status == manager_common.PERDELETE:
                self.status = manager_common.DELETED
                msg = 'Agent %s with id %d set status to DELETED success' % (CONF.host, self.agent_id)
                suicide(delay=3)
                return BaseRpcResult(self.agent_id, ctxt,
                                     resultcode=manager_common.RESULT_SUCCESS, result=msg)
            else:
                msg = 'Agent status is not PERDELETE, status is %d' % self.status
                return BaseRpcResult(self.agent_id, ctxt,
                                     resultcode=manager_common.RESULT_ERROR, result=msg)

    @CheckManagerRpcCtxt
    def rpc_upgrade_agent(self, ctxt, **kwargs):
        last_status = self.status
        if not self.set_status(manager_common.HARDBUSY):
            return BaseRpcResult(self.agent_id, ctxt,
                                 resultcode=manager_common.RESULT_SUCCESS,
                                 result='upgrade faile because can not set status now')
        # TODO call rpm Uvh then restart self
        self.force_status(last_status)
        return BaseRpcResult(self.agent_id, ctxt, resultcode=manager_common.RESULT_SUCCESS,
                             result='upgrade call rpm Uvh success')
