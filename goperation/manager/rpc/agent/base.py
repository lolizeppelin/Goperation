# -*- coding:utf-8 -*-
import os
import sys
import time
import random
import six
import contextlib
import psutil
import subprocess
from collections import namedtuple

import eventlet
from eventlet import hubs

from simpleutil.config import cfg
from simpleutil.log import log as logging
from simpleutil.utils import lockutils
from simpleutil.utils import importutils
from simpleutil.utils import systemutils
from simpleutil.utils import uuidutils
from simpleutil.utils.systemutils import subwait
from simpleutil.utils.attributes import validators

from simpleutil.utils.systemutils import ExitBySIG
from simpleutil.utils.systemutils import UnExceptExit

from simpleservice.loopingcall import IntervalLoopinTask
from simpleservice.plugin.base import EndpointBase


from goperation import threadpool
from goperation.utils import suicide
from goperation.utils import safe_fork
from goperation.utils import get_network
from goperation.api.client import GopHttpClientApi
from goperation.filemanager import FileManager
from goperation.manager.api import get_http
from goperation.manager import common as manager_common
from goperation.manager.utils.validateutils import validate_endpoint
from goperation.manager.utils.targetutils import target_server
from goperation.manager.utils.targetutils import target_endpoint
from goperation.manager.utils.resultutils import AgentRpcResult
from goperation.manager.utils.resultutils import UriResult
from goperation.manager.rpc.base import RpcManagerBase
from goperation.manager.rpc.exceptions import RpcTargetLockException
from goperation.manager.rpc.agent.ctxtdescriptor import CheckManagerRpcCtxt
from goperation.manager.rpc.agent.ctxtdescriptor import CheckThreadPoolRpcCtxt
from goperation.manager.rpc.agent.config import rpc_endpoint_opts


CONF = cfg.CONF

LOG = logging.getLogger(__name__)

WEBSOCKETREADER = 'gop-websocket'
YUM = 'yum'

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
    PROCESSATTR = ['status', 'num_fds', 'num_threads', 'name', 'pid']

    def __init__(self, manager):
        self.manager = manager
        self.with_performance = CONF[manager_common.AGENT].report_performance
        self.probability = CONF[manager_common.AGENT].metadata_flush_probability - 1

        interval = CONF[manager_common.AGENT].online_report_interval
        self.interval = interval*60

        # 计算延迟时间,延迟直至时间点(周期性上报时间点,根据配置, 在1 3 5 6 12分时上报)
        _now = time.time()
        fix = _now - int(_now)
        now = time.gmtime(int(_now)-time.timezone)
        tmin = now.tm_min
        sec = now.tm_sec + fix
        times, mod = divmod(tmin, interval)
        if times > 0:
            delay = ((times + 1) * interval - tmin) * 60 - sec
        else:
            delay = (interval - tmin) * 60 - sec

        self.cpu_stat = None
        self.cpu_times = None
        LOG.debug('Report will execute after %1.2fs at the first time' % delay)
        super(OnlinTaskReporter, self).__init__(periodic_interval=self.interval,
                                                initial_delay=delay,
                                                stop_on_exception=False)

    def __call__(self, *args, **kwargs):

        body = {'metadata': self.metadata,
                'expire': self.interval * 2,
                'snapshot': self.performance_snapshot()}
        try:
            self.manager.client.agent_report(self.manager.agent_id, body)
        except Exception:
            LOG.warning('Agent report fail')
            raise

    def flush_metadata(self, metadata, expire):
        body = {'metadata': metadata,
                'expire': expire,
                'snapshot': None}
        eventlet.spawn_n(self.manager.client.agent_report, self.manager.agent_id, body)

    def flush_performance(self):
        body = {'metadata': None,
                'expire': self.interval * 2,
                'snapshot': self.performance_snapshot()}
        eventlet.spawn_n(self.manager.client.agent_report, self.manager.agent_id, body)

    @property
    def metadata(self):
        # 除第一次外,随机选择是否更新元数据,减少通信量
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
        tmin = now.tm_min
        running = 0
        sleeping = 0
        num_fds = 0
        num_threads = 0
        listen = 0
        syn = 0
        enable = 0
        closeing = 0
        count = 0
        # psutil版本要求5.4+
        for proc in psutil.process_iter(self.PROCESSATTR):
            num_threads += proc.info.get('num_threads')
            num_fds += proc.info.get('num_fds')
            status = proc.info.get('status')
            if status == 'sleeping':
                sleeping += 1
            elif status == 'running':
                running += 1
            else:
                LOG.error('process %s with pid %d status '
                          'not sleeping or running, status %s' %
                          (proc.info.get('name'), proc.info.get('pid'), status))
                continue
            if hasattr(proc, 'connection_iter'):
                proc_iter = proc.connection_iter
            else:
                proc_iter = proc.connections
            try:
                for conn in proc_iter():
                    if count >= 500:
                        count = 0
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
            except psutil.NoSuchProcess:
                continue
        memory = psutil.virtual_memory()
        return dict(date=date, hour=hour, min=tmin,
                    running=running, sleeping=sleeping, num_fds=num_fds, num_threads=num_threads,
                    context=interrupt[0], interrupts=interrupt[1], sinterrupts=interrupt[2],
                    irq=cputimes.irq, sirq=cputimes.softirq,
                    user=cputimes.user, system=cputimes.system,
                    nice=cputimes.nice, iowait=cputimes.iowait,
                    used=memory.used/(1024*1024), cached=memory.cached/(1024*1024),
                    buffers=memory.buffers/(1024*1024), free=memory.free/(1024*1024),
                    left=self.manager.partion_left_size,
                    listen=listen, syn=syn, enable=enable, closeing=closeing)


class Cleaner(IntervalLoopinTask):
    """清理循环,清理过期数据"""

    def __init__(self, manager):
        self.manager = manager
        # 每天检查一次
        super(Cleaner, self).__init__(periodic_interval=86400,
                                      initial_delay=3600,
                                      stop_on_exception=False)

    def __call__(self, *args, **kwargs):
        self.manager.filemanager.clean_expired(day=10)
        for endpoint in self.manager.endpoints:
            endpoint.clean_expired()
            eventlet.sleep(1)


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

    @property
    def endpoint_backup(self):
        return os.path.join(self.endpoint_home, 'backup')

    def pre_start(self, external_objects):
        if not os.path.exists(self._home_path):
            os.makedirs(self._home_path, 0o755)
        if not os.path.exists(self.endpoint_backup):
            os.makedirs(self.endpoint_backup, 0o777)

    @contextlib.contextmanager
    def lock(self, entity, timeout=3):
        while self.frozen:
            if timeout < 1:
                raise RpcTargetLockException(self.namespace, entity, 'endpoint frozen')
            eventlet.sleep(1)
            timeout -= 1
        if timeout < 0:
            timeout = 0
        if len(self.semaphores) >= self.conf.max_lock:
            raise RpcTargetLockException(self.namespace, entity, 'over max lock')
        lock = self.semaphores.get(entity)
        if lock.acquire(blocking=True, timeout=max(0.1, timeout)):
            try:
                yield
            finally:
                lock.release()
        else:
            raise RpcTargetLockException(self.namespace, entity)

    @contextlib.contextmanager
    def locks(self, entitys, timeout=5):
        timeout = float(timeout)
        while self.frozen:
            if timeout < 0.1:
                raise RpcTargetLockException(self.namespace, entitys, 'endpoint frozen')
            eventlet.sleep(0.1)
            timeout -= 0.1
        self.frozen = True
        if len(entitys) + len(self.semaphores) > self.conf.max_lock:
            self.frozen = False
            raise RpcTargetLockException(self.namespace, entitys, 'over max lock')
        success = set()
        for entity in entitys:
            if timeout <= 0.1:
                self.frozen = False
                for _lock in success:
                    _lock.release()
                raise RpcTargetLockException(self.namespace, entity, 'get lock timeout')
            lock = self.semaphores.get(entity)
            _s = time.time()
            if lock.acquire(blocking=True, timeout=max(0.1, timeout)):
                used = time.time() - _s
                timeout -= used
                success.add(lock)
            else:
                self.frozen = False
                for _lock in success:
                    _lock.release()
                raise RpcTargetLockException(self.namespace, entity, 'get lock timeout')
        self.frozen = False
        try:
            yield
        finally:
            for _lock in success:
                _lock.release()

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

    def notify(self, entity, message):
        self.manager.notify(self, entity, message)

    def post_start(self):
        self.entitys_map = self.manager.allocked_ports[self.namespace]

    @property
    def entitys(self):
        return self.entitys_map.keys()

    def clean_expired(self):
        """clean expired data
        """
        self.clean(self.endpoint_backup, 864000)

    @staticmethod
    def clean(path, maxtime):
        now = int(time.time())
        count = 0
        for root, dirs, files in os.walk(path):
            for _file in files:
                if count >= 100:
                    count = 0
                    eventlet.sleep(0)
                count += 1
                fullpath = os.path.join(root, _file)
                try:
                    atime = systemutils.acctime(fullpath)
                    if (now - atime) > maxtime:
                        os.remove(fullpath)
                except (OSError, IOError):
                    continue
            for _dir in dirs:
                if count >= 100:
                    count = 0
                    eventlet.sleep(0)
                count += 1
                fullpath = os.path.join(root, _dir)
                try:
                    atime = systemutils.acctime(fullpath)
                    if not os.listdir(fullpath) and (now - atime) > maxtime:
                        os.rmdir(fullpath)
                except (OSError, IOError):
                    continue


class RpcAgentManager(RpcManagerBase):

    def __init__(self):
        super(RpcAgentManager, self).__init__(target=target_server(self.agent_type, CONF.host, fanout=True))
        interface, self.ipnetwork = get_network(self.local_ip)
        if not self.ipnetwork:
            raise RuntimeError('can not find local ip netmask')
        LOG.debug('Local ip %s/%s on interface %s' % (self.local_ip, self.ipnetwork.netmask, interface))
        global DISK
        DISK = psutil.disk_usage(self.work_path).total/(1024*1024)
        # agent id
        self._agent_id = None
        # port and port and disk space info
        conf = CONF[manager_common.AGENT]
        self.conf = conf
        self.ports_range = validators['type:ports_range_list'](conf.ports_range) if conf.ports_range else []
        # zone mark
        self.zone = conf.zone
        self.dnsnames = conf.dnsnames
        # key: port, value endpoint name
        self.allocked_ports = {}
        # left ports
        self.left_ports = set()
        for p_range in self.ports_range:
            down, up = map(int, p_range.split('-'))
            if down < 1024:
                raise ValueError('Port 1-1024 is not allowed')
            for port in xrange(down, up):
                self.left_ports.add(port)

        # init metadata
        self._metadata = super(RpcAgentManager, self).metadata
        self._metadata.setdefault('agent_type', self.agent_type)
        self._metadata.setdefault('zone', self.zone)
        self._metadata.setdefault('dnsnames', conf.dnsnames)
        # init httpclient
        self.client = AgentManagerClient(httpclient=get_http())
        # init filemanager
        self.filemanager = FileManager(conf=conf,
                                       threadpool=threadpool,
                                       infoget=lambda x: self.client.file_show(x)['data'][0])

        # init endpoint
        if conf.endpoints:
            # endpoint class must be singleton
            for endpoint in conf.endpoints:
                endpoint_group = cfg.OptGroup(endpoint.lower(),
                                              title='endpopint of %s' % endpoint)
                CONF.register_group(endpoint_group)
                CONF.register_opts(rpc_endpoint_opts, endpoint_group)
                endpoint_class = '%s.%s' % (CONF[endpoint_group.name].module,
                                            self.agent_type.capitalize())
                try:
                    cls = importutils.import_class(endpoint_class)
                except Exception:
                    LOG.error('Import class %s of %s fail' % (endpoint_class, endpoint_group.name))
                    raise
                else:
                    obj = cls(manager=self)
                    if not isinstance(obj, RpcAgentEndpointBase):
                        raise TypeError('Endpoint string %s not base from RpcEndpointBase')
                    self.endpoints.add(obj)
        self.endpoint_lock = lockutils.Semaphores()
        self.websockets = dict()
        self.reporter = OnlinTaskReporter(self)

    def in_range(self, port):
        """if port in ports range"""
        for p_range in self.ports_range:
            down, up = map(int, p_range.split('-'))
            if down <= port < up:
                return True
        return False

    @property
    def metadata(self):
        return self._metadata

    def pre_start(self, external_objects):
        super(RpcAgentManager, self).pre_start(external_objects)
        self.filemanager.scanning(strict=True)
        # get agent id of this agent
        # if agent not exist,call create
        self.client.agent_init_self(manager=self)
        # add online report periodic tasks
        self._periodic_tasks.insert(0, self.reporter)
        # clean periodic tasks
        self._periodic_tasks.append(Cleaner(self))
        for endpoint in self.endpoints:
            endpoint.pre_start(self._metadata)

    def post_start(self):
        agent_info = self.client.agent_show(self.agent_id, body={'ports': True, 'entitys': True})['data'][0]
        status = agent_info['status']
        if status <= manager_common.SOFTBUSY:
            raise RuntimeError('Agent can not start, receive status is %d' % status)
        # get port allocked
        remote_endpoints = agent_info['endpoints']
        add_endpoints, delete_endpoints = self._validate_endpoint(remote_endpoints)
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
        # kill all websockets
        for pid in self.websockets:
            executable = self.websockets.get(pid)
            try:
                p = psutil.Process(pid=pid)
                name = p.name()
            except psutil.NoSuchProcess:
                return
            if name == executable:
                p.kill()
        super(RpcAgentManager, self).post_stop()

    def initialize_service_hook(self):
        # check endpoint here
        for endpoint in self.endpoints:
            endpoint.initialize_service_hook()

    def _validate_endpoint(self, endpoints):
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
        return allocked_port

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
        except Exception:
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
        LOG.info('Free ports, delete an entity?')
        for entitys in six.itervalues(self.allocked_ports):
            for entity_ports in six.itervalues(entitys):
                for port in (entity_ports & _ports):
                    LOG.debug('Free port %d' % port)
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

    def change_performance(self):
        """call by endpoint when create or delete entitys"""
        self.reporter.flush_performance()

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
        memory = psutil.virtual_memory()
        mem = memory.cached / (1024 * 1024) + memory.free / (1024 * 1024)
        return AgentRpcResult(self.agent_id, ctxt,
                              resultcode=manager_common.RESULT_SUCCESS,
                              result='%s,%s,%d,%d' % (self.host, self.local_ip,
                                                      self.partion_left_size, mem),
                              details=[dict(detail_id=index, resultcode=manager_common.RESULT_SUCCESS,
                                            result=dict(endpoint=endpoint.namespace,
                                                        entitys=len(endpoint.entitys),
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
        if not systemutils.LINUX:
            return AgentRpcResult(self.agent_id, ctxt, resultcode=manager_common.RESULT_ERROR,
                                  result='upgrade just on redhat system')
        from simpleutil.utils.systemutils import posix
        with self.work_lock.priority(0):
            if threadpool.threads or self.status < manager_common.SOFTBUSY:
                return AgentRpcResult(self.agent_id, ctxt,
                                      resultcode=manager_common.RESULT_ERROR,
                                      result='upgrade fail public thread pool not empty or status error')
            for endpont in self.endpoints:
                endpont.frozen = True
            last_status = self.status
            executable = systemutils.find_executable(YUM)
            # CALL yum --disablerepo=* --enablerepo=goputil clean metadata FIRST
            pid = safe_fork()
            args = [executable, '-y', '--disablerepo=*', '--enablerepo=goputil', 'clean', 'metadata']
            if pid == 0:
                os.closerange(3, systemutils.MAXFD)
                os.execv(executable, args)
            try:
                posix.wait(pid, 5)
            except (ExitBySIG, UnExceptExit):
                self.status = last_status
                return AgentRpcResult(self.agent_id, ctxt, resultcode=manager_common.RESULT_ERROR,
                                      result='upgrade call yum clean metadata fail')
            LOG.info('Call yum clean success')
            args = [executable, '-y', '--disablerepo=*', '--enablerepo=goputil', 'update']
            rpms = ['python-simpleutil-*', 'python-simpleservice-*',
                    'python-simpleflow-*', 'python-goperation-*']
            for cls in self.conf.endpoints:
                rpms.append('python-%s-*' % cls)
            args.extend(rpms)
            LOG.info('Rpm upgrade command %s' % ' '.join(args))

            pid = safe_fork()
            if pid == 0:
                os.closerange(3, systemutils.MAXFD)
                logpath = CONF.log_dir
                logfile = os.path.join(logpath, 'upgrade.%d.log' % int(time.time()))
                with open(logfile, 'ab') as f:
                    os.dup2(f.fileno(), sys.stdout.fileno())
                    os.dup2(f.fileno(), sys.stderr.fileno())
                    # exec后关闭日志文件描述符
                    systemutils.set_cloexec_flag(f.fileno())
                    try:
                        os.execv(executable, args)
                    except (OSError, IOError) as e:
                        sys.stderr.write('exec: ' + ' '.join(args) + '\n')
                        sys.stderr.write(str(e) + '\n')
                        os._exit(1)
            try:
                posix.wait(pid, 600)
            except (ExitBySIG, UnExceptExit) as e:
                self.status = last_status
                return AgentRpcResult(self.agent_id, ctxt, resultcode=manager_common.RESULT_ERROR,
                                      result='upgrade call yum update fail, %s' % e.message)
            executable = '/etc/init.d/gop-%s' % self.agent_type
            args = [executable, 'restart']
            pid = safe_fork()
            if pid == 0:
                os.closerange(3, systemutils.MAXFD)
                ppid = os.fork()
                if ppid == 0:
                    eventlet.sleep(5)
                    os.execv(executable, args)
                os._exit(0)
            posix.wait(pid)
            LOG.warning('Agent restart command executeing, restart in 5 seconds')
            return AgentRpcResult(self.agent_id, ctxt, resultcode=manager_common.RESULT_SUCCESS,
                                  result='upgrade call yum update success')

    def max_websocket(self):
        if len(self.websockets) >= self.conf.websokcets:
            raise ValueError('websockets more then 3, too many websocket process')

    @CheckManagerRpcCtxt
    @CheckThreadPoolRpcCtxt
    def rpc_getfile(self, ctxt, md5, timeout):
        timeout - time.time()
        self.filemanager.get(md5, download=True, timeout=timeout)
        return AgentRpcResult(self.agent_id, ctxt, resultcode=manager_common.RESULT_SUCCESS,
                              result='getfile success')

    def readlog(self, logpath, user, group, lines):
        if os.path.isfile(logpath):
            loghome = os.path.split(logpath)[0]
        elif os.path.isdir(logpath):
            loghome = logpath
        else:
            raise ValueError('Log path is not file or dir')
        if loghome == '/':
            raise ValueError('Log path is root')
        self.max_websocket()
        lines = int(lines)
        executable = systemutils.find_executable(WEBSOCKETREADER)
        token = str(uuidutils.generate_uuid()).replace('-', '')
        args = [executable, '--home', loghome, '--token', token]
        port = max(self.left_ports)
        self.left_ports.remove(port)
        args.extend(['--port', str(port)])
        args.extend(['--lines', str(lines)])
        if LOG.isEnabledFor(logging.DEBUG):
            args.extend(['--logfile', os.path.join(loghome, 'ws.%d.log' % int(time.time()))])
        if self.external_ips:
            ipaddr = self.external_ips[0]
        else:
            ipaddr = self.local_ip
        try:
            with open(os.devnull, 'wb') as nul:
                LOG.debug('Websocket command %s %s' % (executable, ' '.join(args)))
                if systemutils.WINDOWS:
                    sub = subprocess.Popen(executable=executable, args=args,
                                           stdout=nul.fileno(), stderr=nul.fileno(),
                                           close_fds=True)
                    pid = sub.pid
                else:
                    pid = safe_fork(user=user, group=group)
                    if pid == 0:
                        os.dup2(nul.fileno(), sys.stdout.fileno())
                        os.dup2(nul.fileno(), sys.stderr.fileno())
                        os.closerange(3, systemutils.MAXFD)
                        try:
                            os.execv(executable, args)
                        except (OSError, IOError):
                            os._exit(1)
                self.websockets.setdefault(pid, WEBSOCKETREADER)
                LOG.info('Websocket start with pid %d' % pid)

            def _kill():
                try:
                    p = psutil.Process(pid=pid)
                    name = p.name()
                except psutil.NoSuchProcess:
                    return
                if name == WEBSOCKETREADER:
                    LOG.warning('Websocket reader overtime, kill it')
                    p.kill()

            hub = hubs.get_hub()
            _timer = hub.schedule_call_global(3600, _kill)

            def _wait():
                try:
                    if systemutils.POSIX:
                        from simpleutil.utils.systemutils import posix
                        posix.wait(pid)
                    else:
                        subwait(sub)
                except Exception as e:
                    LOG.error('Websocket reader wait catch error %s' % str(e))
                LOG.info('Websocket reader with pid %d has been exit' % pid)
                self.websockets.pop(pid, None)
                _timer.cancel()

            eventlet.spawn_n(_wait)
        finally:
            self.left_ports.add(port)
        return dict(port=port, token=token, ipaddr=ipaddr)

    def notify(self, endpoint, entity, message):
        """NotImplemented notify api"""
        LOG.info('Notify not NotImplemented')
        # entity = entity
        # endpoint = endpoint.namespace
        # agent_id = self.agent_id

    @CheckManagerRpcCtxt
    @CheckThreadPoolRpcCtxt
    def rpc_readlog(self, ctxt, **kwargs):
        lines = int(kwargs.pop('lines', 10))
        logpath = CONF.log_dir
        user = 'nobody'
        group = 'nobody'
        result = 'get agent log success'
        try:
            uri = self.readlog(logpath, user=user, group=group, lines=lines)
        except ValueError as e:
            return UriResult(resultcode=manager_common.RESULT_ERROR,
                                   result='read log fail:%s' % e.message)
        return UriResult(resultcode=manager_common.RESULT_SUCCESS, result=result, uri=uri)

    def rpc_flush_metadata(self, ctxt, **kwargs):
        self.reporter.flush_metadata(self.metadata, kwargs.get('expire'))
        return AgentRpcResult(self.agent_id, ctxt,
                              resultcode=manager_common.RESULT_SUCCESS,
                              result='Agent report has been send')
