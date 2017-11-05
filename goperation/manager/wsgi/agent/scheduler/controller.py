import webob.exc
import time
import datetime

from simpleutil.common.exceptions import InvalidArgument
from simpleutil.utils import jsonutils
from simpleutil.utils import uuidutils


from goperation.manager import common as manager_common
from goperation.manager import targetutils
from goperation.manager import resultutils
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
    {'type': 'object',
     'required': ['jobs', 'start', 'end', ],
     'properties':
         {'jobs': {'type': 'array',                                             # jobs info
                   'minItems': 1,
                   'items': {'type': 'object',
                             'required': ['execute'],
                             'properties': {'execute': {'type': 'object',       # execute job
                                                        'required': ['cls', 'method'],
                                                        'properties': {'cls': {'type': 'string'},
                                                                       'method': {'type': 'string'},
                                                                       'args': {'type': 'object'}
                                                                       }},
                                            'revert': {'type': 'object',        # revert job
                                                       'required': ['cls', 'method'],
                                                       'properties': {'cls': {'type': 'string'},
                                                                      'method': {'type': 'string'},
                                                                      'args': {'type': 'object'}
                                                                      }}}}, },
          'start': {'type': 'string', 'format': 'date-time'},      # jobs start time
          'end': {'type': 'string', 'format': 'date-time'},        # jobs end time
          'deadline': {'type': 'string', 'format': 'date-time'},   # jobs deadline time
          }
     }
}


class SchedulerRequest(object):

    def __init__(self):
        self._all_server_id = set()

    def index(self, req, body):
        return 'index'

    def create(self, req, body=None):
        body = body or {}
        dispose = body.pop('dispose', False)
        jsonutils.schema_validate(body, SCHEDULEJOBSCHEMA)
        start=datetime.datetime.fromtimestamp(body['start']),
        end=datetime.datetime.fromtimestamp(body['end']),
        deadline=datetime.datetime.fromtimestamp(body['deadline'])
        mini_time = int(time.time()) + 300
        if start < mini_time:
            raise InvalidArgument()
        if end < start + 3:
            raise InvalidArgument()
        if deadline:
            raise
        job_id = uuidutils.Gkey()
        rpc = get_client()
        glock = get_global().lock('autorelase')
        with glock(targetutils.schedule_job(), 30):
            job_result = rpc.call(targetutils.target_anyone(manager_common.SCHEDULER),
                                  ctxt={'finishtime': ""},
                                  msg={'method': 'scheduler',
                                       'args': {'job_id': job_id,
                                                'jobdata': body,
                                                'dispose': dispose}})
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
