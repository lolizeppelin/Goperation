from simpleutil.config import cfg
from simpleutil.utils import timeutils
from simpleutil.log import log as logging

from simpleservice.plugin.models import GkeyMap
from simpleservice.ormdb.api import model_query
from simpleservice.ormdb.api import MysqlDriver
from simpleservice.plugin.rpcclient import RPCClientBase
from simpleservice.rpc.config import rpc_client_opts

from goperation import lock
from goperation.redis import GRedisPool
from goperation.manager.config import manager_group
from goperation.manager.config import manager_rabbit_group
from goperation.manager.gdata import GlobalData


LOG = logging.getLogger(__name__)

CONF = cfg.CONF

DbDriver = None
GRedis = None
SERVER_ID = None
RPCClient = None
GlobalDataClient = None


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
    return DbDriver.get_session(read=readonly,
                                autocommit=True,
                                expire_on_commit=False,
                                use_slave=False)


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
                        upquery = model_query(session, GkeyMap, filter={'host': None})
                        upquery.update(dict(host=CONF.host),
                                       update_args={'mysql_limit': 1})
                        result = query.one()
                    SERVER_ID = result.sid
    else:
        LOG.warning("Do not call init_server_id more then once")


def init_redis():
    global GRedis
    if GRedis is not None:
        LOG.warning("Do not call init_redis more then once")
        return
    with lock.get('redis'):
        if GRedis is None:
            if SERVER_ID is None:
                init_server_id()
            conf = CONF[manager_group.name]
            kwargs = dict(server_id=SERVER_ID,
                          max_connections=conf.redis_pool_size,
                          host=conf.redis_host,
                          port=conf.redis_port,
                          db=conf.redis_db,
                          password=conf.redis_password,
                          socket_connect_timeout=conf.redis_connect_timeout,
                          socket_timeout=conf.redis_socket_timeout,
                          heart_beat_over_time=conf.redis_heartbeat_overtime,
                          heart_beat_over_time_max_count=conf.redis_heartbeat_overtime_max_count,
                          )
            redis_client = GRedisPool.from_url(**kwargs)
            redis_client.start()
            GRedis = redis_client


def get_redis():
    if GRedis is None:
        init_redis()
    return GRedis


get_cache = get_redis


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


def init_global_data_client():
    global GlobalDataClient
    if GlobalDataClient is None:
        with lock.get('sync'):
            if GlobalDataClient is None:
                LOG.info("Try init glock client for manager")
                GlobalDataClient = GlobalData(client=get_redis(),
                                              session=get_session)
    else:
        LOG.warning("Do not call init_sync_client more then once")


def get_global():
    if GlobalDataClient is None:
        init_global_data_client()
    return GlobalDataClient


class ManagerRpcClient(RPCClientBase):
    """singleton Rpc client"""
    def __init__(self):
        CONF.register_opts(rpc_client_opts, manager_rabbit_group)
        super(ManagerRpcClient, self).__init__(CONF[manager_rabbit_group.name])
        self.rpcdriver.init_timeout_record(session=get_session(readonly=False))
