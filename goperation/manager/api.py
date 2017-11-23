from requests import Session
from requests import adapters

from simpleutil.config import cfg
from simpleutil.utils import timeutils
from simpleutil.log import log as logging

from simpleservice.plugin.models import GkeyMap
from simpleservice.ormdb.api import model_query
from simpleservice.ormdb.api import MysqlDriver
from simpleservice.plugin.rpcclient import RPCClientBase

from goperation import lock
from goperation.redis import GRedisPool
from goperation.api.client import ManagerClient
from goperation.manager.config import manager_group
from goperation.manager.config import rabbit_conf
from goperation.manager.gdata import GlobalData


LOG = logging.getLogger(__name__)

CONF = cfg.CONF

DbDriver = None
GRedis = None
SERVER_ID = None
RPCClient = None
HTTPClient = None
GlobalDataClient = None


class ManagerRpcClient(RPCClientBase):
    """singleton Rpc client"""
    def __init__(self):
        super(ManagerRpcClient, self).__init__(rabbit_conf)
        self.rpcdriver.init_timeout_record(session=get_session(readonly=False))


def rpcfinishtime(starttime=None):
    rpc_conf = rabbit_conf
    if not starttime:
        starttime = int(timeutils.realnow())
    offset_time = rpc_conf.rpc_send_timeout * (rpc_conf.rpc_send_retry + 1)
    return starttime + offset_time + 5


def init_server_id():
    global SERVER_ID
    if SERVER_ID is None:
        with lock.get('sid'):
            if SERVER_ID is None:
                session = get_session()
                # result = session.query(GkeyMap).filter(GkeyMap.host ==  CONF.host).with_for_update().one_or_none()
                # if not result:
                #     session.query(GkeyMap).filter(GkeyMap.host ==  None).update(dict(host=CONF.host),
                #                                                                 update_args={'mysql_limit': 1})
                #     session.commit()
                # else:
                #     session.commit()
                #     return result.sid
                with session.begin(subtransactions=True):
                    query = model_query(session, GkeyMap, filter=GkeyMap.host == CONF.host)
                    result = query.one_or_none()
                    if not result:
                        upquery = model_query(session, GkeyMap, filter=GkeyMap.host == None)
                        upquery.update(dict(host=CONF.host),
                                       update_args={'mysql_limit': 1})
                        result = query.one()
                    SERVER_ID = result.sid
    else:
        LOG.warning("Do not call init_server_id more then once")


def init_mysql_session():
    global DbDriver
    if DbDriver is None:
        with lock.get('mysql'):
            if DbDriver is None:
                LOG.info("Try connect database for manager, lazy load")
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
                                expire_on_commit=False)


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


def init_global():
    global GlobalDataClient
    if GlobalDataClient is None:
        with lock.get('global'):
            if GlobalDataClient is None:
                LOG.info("Try init glock client for manager")
                GlobalDataClient = GlobalData(client=get_redis(),
                                              session=get_session)
    else:
        LOG.warning("Do not call init_global more then once")


def get_global():
    if GlobalDataClient is None:
        init_global()
    return GlobalDataClient


def init_http_client():
    global HTTPClient
    if HTTPClient is None:
        with lock.get('http'):
            if HTTPClient is None:
                LOG.info("Try init http client for manager")
                conf = CONF[manager_group.name]
                _Session = Session()
                _Session.mount('http://', adapters.HTTPAdapter(pool_connections=1,
                                                               pool_maxsize=conf.http_pconn_count))
                HTTPClient = ManagerClient(url=conf.gcenter,
                                           port=conf.gcenter_port,
                                           token=conf.trusted, session=_Session)
    else:
        LOG.warning("Do not call init_http_client more then once")


def get_http():
    if HTTPClient is None:
        init_http_client()
    return HTTPClient
