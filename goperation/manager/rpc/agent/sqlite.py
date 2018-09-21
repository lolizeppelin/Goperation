import os
from simpleutil.config import cfg
from simpleutil.utils import systemutils

from simpleflow.utils.storage_utils import build_session

from goperation import lock
from goperation.manager import common

CONF = cfg.CONF

TaskflowSession = None


def init_taskflow_session():
    global TaskflowSession
    if TaskflowSession is None:
        with lock.get('taskflow_session'):
            if TaskflowSession is None:
                conf = CONF[common.AGENT]
                if conf.taskflow_connection:
                    connection = conf.taskflow_connection
                else:
                    connection = 'sqlite:///%s' % os.path.join(conf.taskflowcache,
                                                               'taskflow.db')
                    if not os.path.exists(conf.taskflowcache):
                        os.makedirs(conf.taskflowcache, 0o755)
                    if systemutils.LINUX and conf.ramfscache:
                        # TODO mount ramfs on taskflowcache
                        pass
                TaskflowSession = build_session(connection)


def get_taskflow_session():
    if TaskflowSession is None:
        init_taskflow_session()
    return TaskflowSession
