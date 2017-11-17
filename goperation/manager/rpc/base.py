import eventlet

from simpleutil.config import cfg
from simpleutil.utils.lockutils import PriorityLock
from simpleutil.utils.sysemutils import get_partion_free_bytes

from simpleservice.plugin.base import ManagerBase
from simpleservice.rpc.config import rpc_service_opts

from goperation import threadpool
from goperation.filemanager import FileManager
from goperation.manager import common as manager_common
from goperation.manager import config as manager_config
from goperation.manager.rpc import config as rpc_config

CONF = cfg.CONF


class RpcManagerBase(ManagerBase):

    def __init__(self, target, fget):
        super(RpcManagerBase, self).__init__(target=target)
        CONF.register_opts(rpc_service_opts, manager_config.manager_group)
        self.status = manager_common.INITIALIZING
        self.rpcservice = None
        self.work_path = CONF.work_path
        self.local_ip = CONF.local_ip
        self.external_ips = CONF.external_ips
        self.filemanager = FileManager(conf=CONF[rpc_config.filemanager_group.name],
                                       rootpath=self.work_path,
                                       threadpool=threadpool, fget=fget)
        self.work_lock = PriorityLock()
        self.work_lock.set_defalut_priority(priority=5)

    def pre_start(self, external_objects):
        self.filemanager.scanning(strict=True)
        self.rpcservice = external_objects

    def post_stop(self):
        self.filemanager.stop()
        self.rpcservice = None

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
        if not self.work_lock.locked and self.status == manager_common.ACTIVE:
            return True
        return False

    @property
    def partion_left_size(self):
        return get_partion_free_bytes(self.work_path)/(1024*1024)
