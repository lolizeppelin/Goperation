from simpleutil.config import cfg

from simpleutil.log import log as logging
from simpleservice.ormdb.api import MysqlDriver

from goperation.plugin.manager.config import manager_group

LOG = logging.getLogger(__name__)

CONF = cfg.CONF

DbDriver = None
GLockRedis = None


class RedisEmpty(object):

    def __init__(self, *args, **kwargs):
        """"""

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
       pass

def init_mysql_session():
    global DbDriver
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


def init_redis():
    global GLockRedis
    if GLockRedis is None:
        LOG.info("Try connect redis for manager")
        # redis = RedisEmpty(manager_group.name,
        #                    CONF[manager_group.name])
        # redis.start()
        GLockRedis = RedisEmpty
    else:
        LOG.warning("Do not call init_redis more then once")


def get_redis():
    if GLockRedis is None:
        init_redis()
    return GLockRedis


get_glock = get_redis