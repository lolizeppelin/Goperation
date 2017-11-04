import datetime
from simpleutil.utils import uuidutils
from simpleutil.utils import jsonutils

from goperation.manager.models import ScheduleJob
from goperation.manager.models import JobStep

HTTPFUNCSCHEMA = {
    {'type': 'object',
     'required': ['jobs', 'start', 'end',],
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
          'deadline': {'type': 'string', 'format': 'date-time'},   # jobs end time
          }
     }
}


def build_httpfuncjob(jobdata, schedule):
    jsonutils.schema_validate(jobdata, HTTPFUNCSCHEMA)
    start=datetime.datetime.fromtimestamp(jobdata['start']),
    end=datetime.datetime.fromtimestamp(jobdata['end']),
    deadline=datetime.datetime.fromtimestamp(jobdata['deadline'])
    job_id = uuidutils.Gkey()
    yield ScheduleJob(job_id=job_id,
                      schedule=schedule,
                      jobtype='',
                      start=start,
                      end=end,
                      deadline=deadline)
    for index, step in enumerate(jobdata['jobs']):
       yield JobStep(job_id=job_id,
                          step=index,
                          execute=jsonutils.dumps_as_bytes(step['execute']),
                          revert=jsonutils.dumps_as_bytes(step['revert'] if step.get('revert') else None))
