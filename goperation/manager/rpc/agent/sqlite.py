from simpleutil.config import cfg

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
                TaskflowSession = build_session(CONF[common.AGENT].taskflow_storage)


def get_taskflow_session():
    if TaskflowSession is None:
        init_taskflow_session()
    return TaskflowSession
