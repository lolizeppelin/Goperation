import webob.exc
import time
import datetime

from simpleutil.common.exceptions import InvalidArgument
from simpleutil.utils import jsonutils
from simpleutil.utils import uuidutils
from simpleutil.utils import singleton


from goperation.manager import common as manager_common
from goperation.manager.utils import targetutils
from goperation.manager.utils import resultutils
from goperation.manager.api import get_client
from goperation.manager.api import get_session
from goperation.manager.api import get_global
from goperation.manager.models import ScheduleJob
from goperation.manager.models import JobStep

from goperation.manager.wsgi.contorller import BaseContorller
from goperation.manager.wsgi.exceptions import RpcPrepareError
from goperation.manager.wsgi.exceptions import RpcResultError


FAULT_MAP = {InvalidArgument: webob.exc.HTTPClientError}


SCHEDULEJOBSCHEMA = {
     'type': 'object',
     'required': ['jobs', 'start', 'retry', 'revertall', 'desc'],
     'properties':
         {'jobs': {'type': 'array',
                   'items': {'type': 'object',
                             'required': ['executor'],
                             'properties': {
                                 'executor': {'type': 'string'},
                                 'kwargs': {'type': 'object'},
                                 'execute': {'type': 'string'},
                                 'revert': {'type': 'string'},
                                 'method': {'type': 'string'},
                                 'rebind': {'type': 'array', 'minItems': 1, 'items': {'type': 'string'}},
                                 'provides': {'type': 'array', 'minItems': 1, 'items': {'type': 'string'}}
                             }
                   },
          'kwargs': {'type': 'object'},                                     # for taskflow args:stone
          'start': {'type': 'string', 'format': 'date-time'},               # jobs start time
          'times': {'anyOf': [{'type': 'integer', 'minimum': 1},            # jobs run times, null means nolimit
                              {'type': 'null'}]},
          'interval': {'type': 'integer', 'minimum': 0},                    # jobs run interval
          'retry': {'type': 'integer', 'minimum': 0},                                         # jobs retry times
          'revertall': {'type': 'boolean'},                                    # revert all jobs when job fail
          'desc': {'type': 'string'}                                        # job infomation
          }
     }
}


@singleton.singleton
class SchedulerRequest(BaseContorller):

    def __init__(self):
        self._all_server_id = set()

    def index(self, req, body):
        return 'index'

    def create(self, req, body=None):
        body = body or {}
        jsonutils.schema_validate(body, SCHEDULEJOBSCHEMA)
        start = datetime.datetime.fromtimestamp(body['start'])
        if start < int(time.time()) + 300:
            raise InvalidArgument('Do not add a scheduler in 5 min')
        job_id = uuidutils.Gkey()
        rpc = get_client()
        glock = get_global().lock('autorelase')
        with glock(targetutils.schedule_job(), 30):
            job_result = rpc.call(targetutils.target_anyone(manager_common.SCHEDULER),
                                  ctxt={'finishtime': ""},
                                  msg={'method': 'scheduler',
                                       'args': {'job_id': job_id,
                                                'jobdata': body}})        # job interval
            if not job_result:
                raise RpcResultError('delete_agent_precommit result is None')
            if job_result.get('resultcode') != manager_common.RESULT_SUCCESS:
                return resultutils.results(result=job_result.get('result'))
            return resultutils.results(result='Create scheduler job:%d success' % job_id)

    def show(self, req, job_id, body):
        return 'show'

    def update(self, req, job_id, body):
        return 'show'

    def delete(self, req, job_id, body):
        return 'show'

    def stop(self, req, job_id, body):
        return 'show'

    def start(self, req, job_id, body):
        return 'show'
