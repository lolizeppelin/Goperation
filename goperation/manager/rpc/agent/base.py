import os
import time
import eventlet
import six
import random
import contextlib
import psutil

from simpleutil.config import cfg
from simpleutil.log import log as logging
from simpleutil.utils import lockutils
from simpleutil.utils import importutils
from simpleutil.utils.attributes import validators

from simpleservice.loopingcall import IntervalLoopinTask
from simpleservice.plugin.base import EndpointBase


from goperation import threadpool
from goperation.utils import suicide
from goperation.api.client import GopHttpClientApi
from goperation.filemanager import FileManager
from goperation.manager.api import get_http
from goperation.manager import common as manager_common
from goperation.manager.utils.validateutils import validate_endpoint
from goperation.manager.utils.targetutils import target_server
from goperation.manager.utils.targetutils import target_endpoint
from goperation.manager.utils.resultutils import BaseRpcResult
from goperation.manager.rpc.base import RpcManagerBase
from goperation.manager.rpc.exceptions import RpcTargetLockException
from goperation.manager.rpc.agent.config import agent_group
from goperation.manager.rpc.agent.config import rpc_agent_opts
from goperation.manager.rpc.agent.ctxtdescriptor import CheckManagerRpcCtxt
from goperation.manager.rpc.agent.ctxtdescriptor import CheckThreadPoolRpcCtxt
from goperation.manager.rpc.agent.config import rpc_endpoint_opts


CONF = cfg.CONF

LOG = logging.getLogger(__name__)


class AgentManagerClient(GopHttpClientApi):

    def agent_init_self(self,  manager):
        agent_id = self.cache_online(manager.host, manager.local_ip, manager.agent_type)['data'][0]['agent_id']
        if agent_id is None:
            self.agent_create_self(manager)
        else:
            manager.agent_id = agent_id

    def agent_create_self(self, manager):
        """agent notify gcenter add agent"""
        body = dict(host=manager.host,
                    agent_type=manager.agent_type,
                    cpu=psutil.cpu_count(),
                    # memory available MB
                    # memory=psutil.virtual_memory().available/(1024*1024),
                    # memory total MB
                    memory=psutil.virtual_memory().total/(1024*1024),
                    disk=manager.partion_left_size,
                    ports_range=manager.ports_range,
                    endpoints=[endpoint.namespace for endpoint in manager.endpoints],
                    )
        results = self.agent_create(body)
        agent_id = results['data'][0]['agent_id']
        manager.agent_id = agent_id


class OnlinTaskReporter(IntervalLoopinTask):
    """Report Agent online
    """
    def __init__(self, manager):
        self.manager = manager
        self.with_performance = CONF[manager_common.AGENT].report_performance
        interval = CONF[manager_common.AGENT].online_report_interval*60
        # TODO delay time
        super(OnlinTaskReporter, self).__init__(periodic_interval=interval,
                                                initial_delay=random.randint(0, 10),
                                                stop_on_exception=False)

    def __call__(self, *args, **kwargs):
        body = {'agent_ipaddr': self.manager.local_ip,
                'snapshot': self.performance_snapshot()}
        self.manager.client.agent_report(self.manager.agent_id, body)

    def performance_snapshot(self):
        if not self.with_performance:
            return None
        # TODO do a system performance snapshot with psutil
        return None


class RpcAgentEndpointBase(EndpointBase):

    UMASK = 022
    semaphores = lockutils.Semaphores()

    def __init__(self, manager, name):
        if not isinstance(manager, RpcAgentManager):
            raise TypeError('Manager for rpc endpoint is not RpcAgentManager')
        super(EndpointBase, self).__init__(target=target_endpoint(name))
        self.manager = manager
        self.entitys_map = None
        self.conf = CONF[name]
        self.frozen = False
        self._home_path = os.path.join(manager.work_path, self.namespace)

    @property
    def endpoint_home(self):
        return self._home_path

    home = endpoint_home

    def pre_start(self, external_objects):
        if not os.path.exists(self.home):
            os.makedirs(self.home)

    @contextlib.contextmanager
    def lock(self, entity, timeout=3):
        while self.frozen:
            if timeout < 1:
                raise RpcTargetLockException(self.namespace, entity, 'endpoint frozen')
            eventlet.sleep(1)
            timeout -= 1
        if timeout < 0:
            timeout = 0
        if len(self.semaphores) > self.conf.max_lock:
            raise RpcTargetLockException(self.namespace, entity, 'over max lock')
        lock = self.semaphores.get(entity)
        if lock.acquire(blocking=True, timeout=timeout):
            yield
            lock.release()
        else:
            raise RpcTargetLockException(self.namespace, entity)

    def rpc_create_entity(self, ctxt, entity, **kwargs):
        raise NotImplementedError

    def rpc_delete_entitys(self, ctxt, entitys, **kwargs):
        raise NotImplementedError

    @property
    def filemanager(self):
        return self.manager.filemanager

    def post_start(self):
        self.entitys_map = self.manager.allocked_ports[self.namespace]

    @property
    def entitys(self):
        return self.entitys_map.keys()


class RpcAgentManager(RpcManagerBase):

    def __init__(self):
        # init httpclient
        self.client = AgentManagerClient(httpclient=get_http())
        super(RpcAgentManager, self).__init__(target=target_server(self.agent_type, CONF.host, fanout=True))
        self.filemanager = FileManager(conf=CONF[agent_group.name],
                                       rootpath=self.work_path,
                                       threadpool=threadpool, infoget=lambda x: self.client.file_show(x)['data'][0])
        # agent id
        self._agent_id = None
        # port and port and disk space info
        conf = CONF[manager_common.AGENT]
        self.ports_range = validators['type:ports_range_list'](conf.ports_range) if conf.ports_range else []
        # key: port, value endpoint name
        self.allocked_ports = {}
        # left ports
        self.left_ports = set()
        for p_range in self.ports_range:
            up, down = map(int, p_range.split('-'))
            for port in xrange(up, down):
                self.left_ports.add(port)
        # init endpoint
        if CONF.endpoints:
            # endpoint class must be singleton
            for endpoint in CONF.endpoints:
                endpoint_group = cfg.OptGroup(endpoint.lower(),
                                              title='endpopint of %s' % endpoint)
                CONF.register_group(endpoint_group)
                CONF.register_opts(rpc_endpoint_opts, endpoint_group)
                endpoint_class = '%s.%s' % (CONF[endpoint_group.name].module,
                                            self.agent_type.capitalize())
                try:
                    cls = importutils.import_class(endpoint_class)
                    # if not isinstance(cls, RpcEndpointBase):
                    #     raise TypeError('Endpoint class string %s not RpcEndpointBase' % endpoint_class)
                except Exception:
                    LOG.error('Import class of %s faile' % endpoint_group.name)
                    raise
                else:
                    obj = cls(manager=self, name=endpoint_group.name)
                    if not isinstance(obj, RpcAgentEndpointBase):
                        raise TypeError('Endpoint string %s not base from RpcEndpointBase')
                    self.endpoints.add(obj)
        self.endpoint_lock = lockutils.Semaphores()

    def pre_start(self, external_objects):
        super(RpcAgentManager, self).pre_start(external_objects)
        self.filemanager.scanning(strict=True)
        # get agent id of this agent
        # if agent not exist,call create
        self.client.agent_init_self(manager=self)
        # add online report periodic tasks
        self._periodic_tasks.insert(0, OnlinTaskReporter(self))
        for endpoint in self.endpoints:
            endpoint.pre_start(self._periodic_tasks)

    def post_start(self):
        agent_info = self.client.agent_show(self.agent_id, body={'ports': True, 'entitys': True})['data'][0]
        status = agent_info['status']
        if status <= manager_common.SOFTBUSY:
            raise RuntimeError('Agent can not start, receive status is %d' % status)
        # get port allocked
        remote_endpoints = agent_info['endpoints']
        add_endpoints, delete_endpoints = self.validate_endpoint(remote_endpoints)
        for endpoint in add_endpoints:
            self.allocked_ports.setdefault(endpoint, dict())
        for endpoint, entitys in six.iteritems(remote_endpoints):
            self.allocked_ports.setdefault(endpoint, dict())
            if endpoint in delete_endpoints:
                if entitys:
                    raise RuntimeError('Agent endpoint entity not zero, '
                                       'but not endpoint %s in this agent' % endpoint)
            for _entity in entitys:
                entity = _entity['entity']
                ports = _entity['ports']
                if ports:
                    if None in ports:
                        raise RuntimeError('None in ports list')
                    self.frozen_port(endpoint, entity, ports)
        if delete_endpoints:
            self.client.agents_delete_endpoints(agent_id=self.agent_id, endpoint=list(delete_endpoints))
        if add_endpoints:
            self.client.endpoints_add(agent_id=self.agent_id, endpoints=list(add_endpoints))
        remote_ports_range = agent_info['ports_range']
        if remote_ports_range != self.ports_range:
            LOG.warning('Agent ports range has been changed at remote database')
            body = {'ports_range': self.ports_range}
            # call agent change ports_range
            self.client.agent_edit(agent_id=self.agent_id, body=body)
        # agent set status at this moment
        # before status set, all rpc will requeue by RPCDispatcher
        # so function agent_show in wsgi server do not need agent lock
        self.force_status(status)
        for endpoint in self.endpoints:
            endpoint.post_start()
        super(RpcAgentManager, self).post_start()

    def post_stop(self):
        """close all endpoint here"""
        for endpoint in self.endpoints:
            endpoint.post_stop()
        self.filemanager.stop()
        super(RpcAgentManager, self).post_stop()

    def initialize_service_hook(self):
        # check endpoint here
        for endpoint in self.endpoints:
            endpoint.initialize_service_hook()

    def validate_endpoint(self, endpoints):
        remote_endpoints = set()
        for endpoint in six.iterkeys(endpoints):
            remote_endpoints.add(validate_endpoint(endpoint))
        local_endpoints = set([endpoint.namespace for endpoint in self.endpoints])
        add_endpoints = local_endpoints - remote_endpoints
        delete_endpoints = remote_endpoints - local_endpoints
        return add_endpoints, delete_endpoints

    def frozen_port(self, endpoint, entity, ports):
        allocked_port = set()
        if not isinstance(ports, (list, tuple, set, frozenset)):
            raise TypeError('ports must be a list')
        for port in ports:
            try:
                if port is not None:
                    self.left_ports.remove(port)
                else:
                    port = self.left_ports.pop()
            except KeyError:
                LOG.error('Agent allocked port fail')
                for p in allocked_port:
                    self.left_ports.add(p)
                raise
            if entity not in self.allocked_ports[endpoint]:
                self.allocked_ports[endpoint][entity] = set()
            self.allocked_ports[endpoint][entity].add(port)
            allocked_port.add(port)
        return allocked_port

    def free_ports(self, ports):
        _ports = set()
        if isinstance(ports, (int, long)):
            _ports.add(ports)
        else:
            _ports = set(ports)
        for entitys in six.itervalues(self.allocked_ports):
            for entity_ports in six.itervalues(entitys):
                for port in (entity_ports & _ports):
                    entity_ports.remove(port)
                    _ports.remove(port)
                    self.left_ports.add(port)
        if _ports:
            LOG.error('%d port can not be found after free ports' % len(_ports))
        return _ports

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
                             details=[dict(detail_id=index, resultcode=manager_common.RESULT_SUCCESS,
                                           result=dict(endpoint=endpoint.namespace,
                                                       entitys=endpoint.entitys,
                                                       locked=len(endpoint.semaphores),
                                                       frozen=endpoint.frozen))
                                      for index, endpoint in enumerate(self.endpoints)])

    @CheckManagerRpcCtxt
    def rpc_delete_agent_precommit(self, ctxt, **kwargs):
        with self.work_lock.priority(0):
            if threadpool.threads:
                return BaseRpcResult(self.agent_id, ctxt,
                                     resultcode=manager_common.RESULT_ERROR,
                                     result='Thread pool is not empty')
            for endpont in self.endpoints:
                endpont.frozen = True
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
                if endpont.entitys:
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
        with self.work_lock.priority(0):
            if threadpool.threads or self.status < manager_common.SOFTBUSY:
                return BaseRpcResult(self.agent_id, ctxt,
                                     resultcode=manager_common.RESULT_ERROR,
                                     result='upgrade fail public thread pool not empty or status error')
            for endpont in self.endpoints:
                endpont.frozen = True
            last_status = self.status
            self.status = manager_common.HARDBUSY
            # TODO call rpm Uvh then restart self
            self.status = last_status
            return BaseRpcResult(self.agent_id, ctxt, resultcode=manager_common.RESULT_SUCCESS,
                                 result='upgrade call rpm Uvh success')

    @CheckManagerRpcCtxt
    @CheckThreadPoolRpcCtxt
    def getfile(self, ctxt, mark, timeout):
        timeout - time.time()
        self.filemanager.get(mark, download=True, timeout=timeout)
        return BaseRpcResult(self.agent_id, ctxt, resultcode=manager_common.RESULT_SUCCESS,
                             result='getfile success')
