import os
from simpleutil.config import cfg
from simpleutil.utils.lockutils import PriorityLock
from simpleutil.utils.systemutils import get_partion_free_bytes

from simpleservice.plugin.base import ManagerBase
from simpleservice.rpc.driver.config import rpc_service_opts

from goperation.manager import common as manager_common
from goperation.manager import config as manager_config

CONF = cfg.CONF


class RpcManagerBase(ManagerBase):

    def __init__(self, target):
        super(RpcManagerBase, self).__init__(target=target)
        self.rpcservice = None
        CONF.register_opts(rpc_service_opts, manager_config.rabbit_group)
        self.rabbit_conf = CONF[manager_config.rabbit_group.name]
        self.host = CONF.host
        self.work_path = CONF.work_path
        if not os.path.exists(self.work_path):
            os.makedirs(self.work_path)
        self.local_ip = CONF.local_ip
        self.external_ips = CONF.external_ips
        self.work_lock = PriorityLock()
        self.work_lock.set_defalut_priority(priority=5)
        self.status = manager_common.INITIALIZING

    def pre_start(self, external_objects):
        if self.work_path == '/':
            raise RuntimeError('Work path is root path')
        self.rpcservice = external_objects

    def post_stop(self):
        self.rpcservice = None

    @property
    def is_active(self):
        if not self.work_lock.locked and self.status == manager_common.ACTIVE:
            return True
        return False

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
    def partion_left_size(self):
        return get_partion_free_bytes(self.work_path)/(1024*1024)

    @property
    def attributes(self):
        return dict(local_ip=self.local_ip,
                    external_ips=self.external_ips,
                    host=self.host)
