# -*- coding:utf-8 -*-
import os
import time
import random
import eventlet
import six
import contextlib
import psutil
from netaddr import IPNetwork
from collections import namedtuple

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
from goperation.manager.utils.resultutils import AgentRpcResult
from goperation.manager.rpc.base import RpcManagerBase
from goperation.manager.rpc.exceptions import RpcTargetLockException
from goperation.manager.rpc.agent.ctxtdescriptor import CheckManagerRpcCtxt
from goperation.manager.rpc.agent.ctxtdescriptor import CheckThreadPoolRpcCtxt
from goperation.manager.rpc.agent.config import rpc_endpoint_opts


CONF = cfg.CONF

LOG = logging.getLogger(__name__)


CPU = psutil.cpu_count()
MEMORY = psutil.virtual_memory().total/(1024*1024)
DISK = 0

CPUINFO = ['irq', 'softirq', 'user', 'system', 'nice', 'iowait']

scputimes = namedtuple('scputimes', CPUINFO)


class AgentManagerClient(GopHttpClientApi):

    def agent_init_self(self,  manager):
        interval = CONF[manager_common.AGENT].online_report_interval
        agent_id = self.cache_online(agent_type=manager.agent_type,
                                     metadata=manager.metadata,
                                     expire=interval*60)['data'][0]['agent_id']
        if agent_id is None:
            self.agent_create_self(manager)
        else:
            manager.agent_id = agent_id

    def agent_create_self(self, manager):
        """agent notify gcenter add agent"""
        body = dict(host=manager.host,
                    agent_type=manager.agent_type,
                    cpu=CPU,
                    memory=MEMORY,
                    disk=DISK,
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
        self.probability = CONF[manager_common.AGENT].probability - 1

        interval = CONF[manager_common.AGENT].online_report_interval
        self.interval = interval*60

        _now = time.time()
        fix = _now - int(_now)
        now = time.gmtime(int(_now)-time.timezone)
        min = now.tm_min
        sec = now.tm_sec + fix
        times, mod = divmod(min, interval)
        if times > 0:
            delay = ((times+1)*interval - min)*60 - sec
        else:
            delay = (interval-min)*60 - sec

        super(OnlinTaskReporter, self).__init__(periodic_interval=self.interval,
                                                initial_delay=delay,
                                                stop_on_exception=False)
        self.cpu_stat = None
        self.cpu_times = None

    def __call__(self, *args, **kwargs):

        body = {'metadata': self.metadata,
                'expire': self.interval,
                'snapshot': self.performance_snapshot()}
        try:
            self.manager.client.agent_report(self.manager.agent_id, body)
        except Exception:
            LOG.warning('Agent report fail')
            raise

    @property
    def metadata(self):
        # 除第一次外,随机更新元数据
        if not self.cpu_stat:
            return self.manager.metadata
        if not random.randint(0, self.probability):
            return self.manager.metadata
        return None

    def get_cpuinfo(self):
        cpu_stat = psutil.cpu_stats()
        cpu_times = psutil.cpu_times()

        if self.cpu_stat is None:
            self.cpu_stat = cpu_stat
            self.cpu_times = cpu_times
            return None, None
        else:
            interrupt = ((cpu_stat.ctx_switches - self.cpu_stat.ctx_switches)/self.interval,
                         (cpu_stat.interrupts - self.cpu_stat.interrupts)/self.interval,
                         (cpu_stat.soft_interrupts - self.cpu_stat.soft_interrupts)/self.interval)

            # count cpu times, copy from psutil
            all_delta = sum(cpu_times) - sum(self.cpu_times)
            nums = []
            for field in CPUINFO:
                field_delta = getattr(cpu_times, field) - getattr(self.cpu_times, field)
                try:
                    field_perc = (100 * field_delta) / all_delta
                except ZeroDivisionError:
                    field_perc = 0
                field_perc = int(field_perc)
                if field_perc > 100:
                    field_perc = 100
                elif field_perc <= 0:
                    field_perc = 0
                nums.append(field_perc)

            self.cpu_stat = cpu_stat
            self.cpu_times = cpu_times
            return interrupt, scputimes._make(nums)

    def performance_snapshot(self):
        if not self.with_performance:
            return None
        interrupt, cputimes = self.get_cpuinfo()
        if interrupt is None:
            return
        now = time.gmtime(int(time.time())-time.timezone)
        date = '%04d-%02d-%02d' % (now.tm_year, now.tm_mon, now.tm_mday)
        hour = now.tm_hour
        min = now.tm_min
        running = 0
        sleeping = 0
        num_fds = 0
        num_threads = 0
        listen = 0
        syn = 0
        enable = 0
        closeing = 0
        for proc in psutil.process_iter(attrs=['status', 'num_fds', 'num_threads']):
            num_threads += proc.info.get('num_threads')
            num_fds += proc.info.get('num_fds')
            status = proc.info.get('status')
            if status == 'sleeping':
                sleeping += 1
            elif status == 'running':
                running += 1
            else:
                LOG.error('process status not sleeping or running')
            # for conn in proc.info.get('connections'):
            count = 0
            if hasattr(proc, 'connection_iter'):
                proc_iter = proc.connection_iter
            else:
                proc_iter = proc.connections
            try:
                for conn in proc_iter():
                    if not (count % 100):
                        eventlet.sleep(0)
                    if conn.status == 'LISTEN':
                        listen += 1
                    if conn.status == 'SYN_SENT':
                        syn += 1
                    elif conn.status == 'ESTABLISHED':
                        enable += 1
                    elif conn.status == 'CLOSING':
                        closeing += 1
                    count += 1
            except (psutil.NoSuchProcess):
                continue
        memory = psutil.virtual_memory()
        return dict(date=date, hour=hour, min=min,
                    running=running, sleeping=sleeping, num_fds=num_fds, num_threads=num_threads,
                    context=interrupt[0], interrupts=interrupt[1], sinterrupts=interrupt[2],
                    irq=cputimes.irq, sirq=cputimes.softirq,
                    user=cputimes.user, system=cputimes.system,
                    nice=cputimes.nice, iowait=cputimes.iowait,
                    used=memory.used/(1024*1024), cached=memory.cached/(1024*1024),
                    buffers=memory.buffers/(1024*1024), free=memory.free/(1024*1024),
                    left=self.manager.partion_left_size,
                    listen=listen, syn=syn, enable=enable, closeing=closeing)


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
            os.makedirs(self.home, 0755)

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
        if lock.acquire(blocking=True, timeout=max(0.1, timeout)):
            try:
                yield
            finally:
                lock.release()
        else:
            raise RpcTargetLockException(self.namespace, entity)

    @property
    def locked(self):
        return self.semaphores.locked()

    def rpc_create_entity(self, ctxt, entity, **kwargs):
        raise NotImplementedError

    def rpc_post_create_entity(self, ctxt, entity, **kwargs):
        raise NotImplementedError

    def rpc_delete_entity(self, ctxt, entity, **kwargs):
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
        super(RpcAgentManager, self).__init__(target=target_server(self.agent_type, CONF.host, fanout=True))
        self.ipnetwork = None
        for interface, nets in six.iteritems(psutil.net_if_addrs()):
            if self.ipnetwork:
                break
            for net in nets:
                if net.address == self.local_ip:
                    self.ipnetwork =  IPNetwork('%s/%s' % (self.local_ip, net.netmask))
                    LOG.info('Local ip %s/%s on interface %s' % (self.local_ip, net.netmask, interface))
                    break
        if not self.ipnetwork:
            raise RuntimeError('can not find local ip netmask')
        global DISK
        DISK = psutil.disk_usage(self.work_path).total/(1024*1024)
        # agent id
        self._agent_id = None
        # port and port and disk space info
        conf = CONF[manager_common.AGENT]
        self.ports_range = validators['type:ports_range_list'](conf.ports_range) if conf.ports_range else []
        # zone mark
        self.zone = conf.zone
        # key: port, value endpoint name
        self.allocked_ports = {}
        # left ports
        self.left_ports = set()
        for p_range in self.ports_range:
            up, down = map(int, p_range.split('-'))
            for port in xrange(up, down):
                self.left_ports.add(port)

        # init metadata
        self._metadata = super(RpcAgentManager, self).metadata
        self._metadata.setdefault('agent_type', self.agent_type)
        self._metadata.setdefault('zone', self.zone)
        # init httpclient
        self.client = AgentManagerClient(httpclient=get_http())
        # init filemanager
        self.filemanager = FileManager(conf=conf,
                                       threadpool=threadpool,
                                       infoget=lambda x: self.client.file_show(x)['data'][0])

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
                    LOG.error('Import class %s of %s fail' % (endpoint_class, endpoint_group.name))
                    raise
                else:
                    obj = cls(manager=self)
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
            endpoint.pre_start(self._metadata)

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
                self.allocked_ports[endpoint][entity] = set()
                if ports:
                    if None in ports:
                        raise RuntimeError('None in ports list')
                    self._frozen_ports(endpoint, entity, ports)
        if delete_endpoints:
            self.client.endpoints_delete(agent_id=self.agent_id, endpoint=list(delete_endpoints))
        if add_endpoints:
            self.client.endpoints_add(agent_id=self.agent_id, endpoints=list(add_endpoints))
        hardware_changes = {}
        remote_ports_range = agent_info['ports_range']
        if remote_ports_range != self.ports_range:
            LOG.warning('Agent ports range has been changed at remote database')
            hardware_changes.setdefault('ports_range', self.ports_range)
        if agent_info['cpu'] != CPU:
            hardware_changes.setdefault('cpu', CPU)
        if agent_info['memory'] != MEMORY:
            hardware_changes.setdefault('memory', MEMORY)
        if agent_info['disk'] != DISK:
            hardware_changes.setdefault('disk', DISK)
        # call agent change hardware info
        if hardware_changes:
            self.client.agent_edit(agent_id=self.agent_id, body=hardware_changes)
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

    def _frozen_ports(self, endpoint, entity, ports):
        allocked_port = set()
        if not isinstance(ports, (list, tuple, set, frozenset)):
            raise TypeError('ports must be a list')
        if not ports:
            raise ValueError('Ports list is empty')
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
                    self.allocked_ports[endpoint][entity].remove(p)
                raise
            self.allocked_ports[endpoint][entity].add(port)
            allocked_port.add(port)
        return  allocked_port

    @contextlib.contextmanager
    def frozen_ports(self, endpoint, entity, ports):
        LOG.info('frozen port for %s:%d' % (endpoint, entity))
        is_new = False
        if entity not in self.allocked_ports[endpoint]:
            is_new = True
            self.allocked_ports[endpoint][entity] = set()
        allocked_port = self._frozen_ports(endpoint, entity, ports)
        try:
            yield allocked_port
        except:
            LOG.info('sub wrok fail, free port from %s:%d' % (endpoint, entity))
            self.free_ports(allocked_port)
            if is_new:
                self.allocked_ports[endpoint].pop(entity, None)
            raise

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

    def add_entity(self, endpoint, entity):
        if entity in self.allocked_ports[endpoint]:
            LOG.error('Add entity %d to %s faile' % (entity, endpoint))
            raise RuntimeError('entity exist')
        self.allocked_ports[self.namespace][entity] = set()

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
            return AgentRpcResult(self.agent_id, ctxt,
                                 resultcode=manager_common.RESULT_ERROR,
                                 result='ACTIVE agent failure, agent id or ip not match')
        status = kwargs.get('status')
        if not isinstance(status, (int, long)) or status <= manager_common.SOFTBUSY:
            return AgentRpcResult(self.agent_id, ctxt,
                                 resultcode=manager_common.RESULT_ERROR,
                                 result='Agent change status failure, status code value error')
        if not self.set_status(status):
            return AgentRpcResult(self.agent_id, ctxt,
                                 resultcode=manager_common.RESULT_ERROR,
                                 result='ACTIVE agent failure, can not set stauts now')
        return AgentRpcResult(self.agent_id, ctxt,
                             resultcode=manager_common.RESULT_SUCCESS, result='ACTIVE agent success')

    @CheckManagerRpcCtxt
    def rpc_status_agent(self, ctxt, **kwargs):
        return AgentRpcResult(self.agent_id, ctxt,
                             resultcode=manager_common.RESULT_SUCCESS,
                             result='Get status from %s success' % self.local_ip,
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
                return AgentRpcResult(self.agent_id, ctxt,
                                     resultcode=manager_common.RESULT_ERROR,
                                     result='Thread pool is not empty')
            for endpont in self.endpoints:
                endpont.frozen = True
            if self.status <= manager_common.SOFTBUSY:
                return AgentRpcResult(self.agent_id, ctxt,
                                     resultcode=manager_common.RESULT_ERROR,
                                     result='Can not change status now')
            if kwargs['agent_id'] != self.agent_id \
                    or kwargs['agent_type'] != self.agent_type \
                    or kwargs['host'] != CONF.host \
                    or kwargs['agent_ipaddr'] != self.local_ip:
                return AgentRpcResult(self.agent_id, ctxt,
                                     resultcode=manager_common.RESULT_ERROR,
                                     result='Not match this agent')
            for endpont in self.endpoints:
                if endpont.entitys:
                    return AgentRpcResult(self.agent_id, ctxt,
                                         resultcode=manager_common.RESULT_ERROR,
                                         result='Endpoint %s is not empty' % endpont.name)
            self.status = manager_common.PERDELETE
            msg = 'Agent %s with id %d wait delete' % (CONF.host, self.agent_id)
            LOG.info(msg)
            return AgentRpcResult(self.agent_id, ctxt,
                                 resultcode=manager_common.RESULT_SUCCESS, result=msg)

    @CheckManagerRpcCtxt
    def rpc_delete_agent_postcommit(self, ctxt, **kwargs):
        with self.work_lock.priority(0):
            if kwargs['agent_id'] != self.agent_id or \
                            kwargs['agent_type'] != self.agent_type or \
                            kwargs['host'] != CONF.host or \
                            kwargs['agent_ipaddr'] != self.local_ip:
                return AgentRpcResult(self.agent_id, ctxt,
                                     resultcode=manager_common.RESULT_ERROR, result='Not match this agent')
            if self.status == manager_common.PERDELETE:
                self.status = manager_common.DELETED
                msg = 'Agent %s with id %d set status to DELETED success' % (CONF.host, self.agent_id)
                suicide(delay=3)
                return AgentRpcResult(self.agent_id, ctxt,
                                     resultcode=manager_common.RESULT_SUCCESS, result=msg)
            else:
                msg = 'Agent status is not PERDELETE, status is %d' % self.status
                return AgentRpcResult(self.agent_id, ctxt,
                                     resultcode=manager_common.RESULT_ERROR, result=msg)

    @CheckManagerRpcCtxt
    def rpc_upgrade_agent(self, ctxt, **kwargs):
        with self.work_lock.priority(0):
            if threadpool.threads or self.status < manager_common.SOFTBUSY:
                return AgentRpcResult(self.agent_id, ctxt,
                                     resultcode=manager_common.RESULT_ERROR,
                                     result='upgrade fail public thread pool not empty or status error')
            for endpont in self.endpoints:
                endpont.frozen = True
            last_status = self.status
            self.status = manager_common.HARDBUSY
            # TODO call rpm Uvh then restart self
            self.status = last_status
            return AgentRpcResult(self.agent_id, ctxt, resultcode=manager_common.RESULT_SUCCESS,
                                 result='upgrade call rpm Uvh success')

    @CheckManagerRpcCtxt
    @CheckThreadPoolRpcCtxt
    def getfile(self, ctxt, mark, timeout):
        timeout - time.time()
        self.filemanager.get(mark, download=True, timeout=timeout)
        return AgentRpcResult(self.agent_id, ctxt, resultcode=manager_common.RESULT_SUCCESS,
                             result='getfile success')

    @property
    def metadata(self):
        return self._metadata
