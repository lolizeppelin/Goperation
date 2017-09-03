from simpleutil.config import cfg
from simpleutil.utils import timeutils
from simpleutil.utils import lockutils
from simpleutil.log import log as logging

from glockredis.client import ApiRedis
from glockredis.context import GlockContext

from simpleservice.plugin.models import GkeyMap
from simpleservice.ormdb.api import model_query
from simpleservice.ormdb.api import MysqlDriver
from simpleservice.plugin.rpcclient import RPCClientBase
from simpleservice.rpc.config import rpc_client_opts

from goperation.plugin.manager.config import manager_group
from goperation.plugin.manager.config import manager_rabbit_group

LOG = logging.getLogger(__name__)

CONF = cfg.CONF

DbDriver = None
GLockRedis = None
SERVER_ID = None
RPCClient = None

# double lock for init mysql server_id and redis
lock = lockutils.Semaphores()


def init_mysql_session():
    global DbDriver
    if DbDriver is None:
        with lock.get('mysql'):
            if DbDriver is None:
                LOG.info("Try connect database for manager")
                mysql_driver = MysqlDriver(manager_group.name,
                                           CONF[manager_group.name])
                mysql_driver.start()
                DbDriver = mysql_driver
    else:
        LOG.warning("Do not call init_mysql_session more then once")


def get_session(readonly=False):
    if DbDriver is None:
        init_mysql_session()
        # raise RuntimeError('Database not connected')
    if readonly:
        return DbDriver.rsession
    return DbDriver.session


def init_server_id():
    global SERVER_ID
    if SERVER_ID is None:
        with lock.get('sid'):
            if SERVER_ID is None:
                session = get_session()
                with session.begin():
                    query = model_query(session, GkeyMap, filter={'host': CONF.host})
                    result = query.one_or_none()
                    if not result:
                        upquery = model_query(session, GkeyMap)
                        upquery.update(dict(host=CONF.host),
                                       update_args={'mysql_limit': 1})
                        result = query.first()
                    SERVER_ID = result.sid
    else:
        LOG.warning("Do not call init_server_id more then once")


def init_redis():
    global GLockRedis
    if GLockRedis is not None:
        LOG.warning("Do not call init_redis more then once")
        return
    with lock.get('redis'):
        if GLockRedis is None:
            if SERVER_ID is None:
                init_server_id()
            conf = CONF[manager_group.name]
            rs = ApiRedis(SERVER_ID, conf)
            rs.start(conf.redis_connect_timeout)
            GLockRedis = rs


def get_redis():
    if GLockRedis is None:
        init_redis()
    return GLockRedis


def get_cache():
    return get_redis()


def init_rpc_client():
    global RPCClient
    if RPCClient is None:
        with lock.get('rpc'):
            if RPCClient is None:
                LOG.info("Try init rpc client for manager")
                RPCClient = ManagerRpcClient()
    else:
        LOG.warning("Do not call init_rpc_client more then once")


def get_client():
    if RPCClient is None:
        init_rpc_client()
    return RPCClient


def rpcfinishtime(starttime=None):
    rpc_conf = CONF[manager_rabbit_group.name]
    if not starttime:
        starttime = int(timeutils.realnow())
    offset_time = rpc_conf.rpc_send_timeout * (rpc_conf.rpc_send_retry + 1)
    return starttime + offset_time + 4


class mlock(GlockContext):
    """class for global redis lock"""

    def __init__(self, server_list, locktime=15.0, alloctime=1.0):
        """locktime  lock time  seconds
        alloctime  time of alloc lock  seconds
        """
        super(mlock, self).__init__(get_redis(), server_list, locktime, alloctime)


class ManagerRpcClient(RPCClientBase):
    """singleton Rpc client"""
    def __init__(self):
        CONF.register_opts(rpc_client_opts, manager_rabbit_group)
        super(ManagerRpcClient, self).__init__(CONF[manager_rabbit_group.name])
        self.rpcdriver.init_timeout_record(session=get_session())
