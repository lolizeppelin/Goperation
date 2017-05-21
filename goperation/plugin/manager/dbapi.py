from simpleutil.config import cfg

from simpleutil.log import log as logging
from simpleservice.ormdb.api import MysqlDriver

from goperation.plugin.manager.config import manager_group

LOG = logging.getLogger(__name__)

CONF = cfg.CONF

DbDriver = None


def init_session():
    global DbDriver
    if DbDriver is None:
        LOG.info("Try connect database for manager")
        mysql_driver = MysqlDriver(manager_group.name,
                                   CONF[manager_group.name])
        mysql_driver.start()
        DbDriver = mysql_driver
    else:
        LOG.warning("Do not call init_session more then once")


def get_session(readonly=False):
    if DbDriver is None:
        init_session()
        # raise RuntimeError('Database not connected')
    if readonly:
        return DbDriver.rsession
    return DbDriver.session
