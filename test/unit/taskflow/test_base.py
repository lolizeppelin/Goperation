from goperation.taskflow import base
from goperation.manager.rpc.agent.application.taskflow import middleware

from test.unit.taskflow import test_group
from test.unit.taskflow import TestEndpoint
from test.unit.taskflow import TestManager

mananager = TestManager('/root')

endpoint = TestEndpoint(manager=mananager, group=test_group)

_middleware = middleware.EntityMiddleware(entity=1, endpoint=endpoint)

try:
    cs = base.StandardTask(_middleware, rebind=['wtf'])
except Exception as e:
    print 'catch exception', e
    print 'StandardTask test success'

class TestTask(base.StandardTask):

    def execute(self, *args, **kwargs):
        pass

new_cs = TestTask(_middleware)

print 'all test success'