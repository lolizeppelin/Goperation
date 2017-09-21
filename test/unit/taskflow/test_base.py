from goperation.manager.rpc.agent.application.taskflow import middleware
from goperation.taskflow import base



_middleware = middleware.EntityMiddleware(entity=1,
                                          endpoint='mszl',
                                          entity_home='/root',
                                          entity_apppath='entity',
                                          entity_logpath='entity',
                                          entity_user=None,
                                          entity_group=None,
                                          appcation=None,
                                          databases=None
                                          )

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