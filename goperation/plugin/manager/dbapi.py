from eventlet import patcher

from glockredis.context import GlockContext

from simpleutil.config import cfg

from simpleutil.log import log as logging
from simpleservice.ormdb.api import MysqlDriver

from goperation.plugin.manager.config import manager_group
from goperation.plugin.utils import redis

from simpleservice.plugin.models import GkeyMap
from simpleservice.ormdb.api import model_query

LOG = logging.getLogger(__name__)

CONF = cfg.CONF

DbDriver = None
GLockRedis = None
SERVER_ID = None

# double lock from init mysql server_id and redis
_mysql_lock = patcher.original('threading').Lock()
_redis_lock = patcher.original('threading').Lock()
_server_id_lock = patcher.original('threading').Lock()

def init_mysql_session():
    global DbDriver
    if DbDriver is None:
        with _mysql_lock:
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
        with _server_id_lock:
            if SERVER_ID is None:
                session = get_session()
                with session:
                    query = model_query(session, GkeyMap, filter={'host': CONF.host})
                    result = query.first()
                    if not result:
                        upquery = model_query(session, GkeyMap).limit(1)
                        upquery.update(dict(host=CONF.host))
                        upquery.flush()
                        result = query.first()
                    SERVER_ID = result.sid
    else:
        LOG.warning("Do not call init_server_id more then once")


def init_redis():
    global GLockRedis
    if GLockRedis is not None:
        LOG.warning("Do not call init_redis more then once")
        return
    with _redis_lock:
        if GLockRedis is None:
            if SERVER_ID is None:
                init_server_id()
            conf = CONF[manager_group.name]

            rs = redis(SERVER_ID, conf)
            rs.start(conf.redis_connect_timeout*5000)
            GLockRedis = rs


def get_redis():
    if GLockRedis is None:
        init_redis()
    return GLockRedis


class mlock(GlockContext):

    def __init__(self, server_list, locktime=10, alloctime=1.0):
        super(mlock, self).__init__(get_redis(), server_list, locktime, alloctime)
