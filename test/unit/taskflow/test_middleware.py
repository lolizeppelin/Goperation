import time
print time.time()
from goperation.manager.rpc.agent.application.taskflow import middleware
from goperation.taskflow import common
print time.time()


_middleware = middleware.EntityMiddleware(entity=1,
                                          endpoint='mszl',
                                          entity_home='/root',
                                          entity_user=None,
                                          entity_group=None,
                                          appcation=None,
                                          databases=None
                                          )

# print _middleware
_middleware.set_return('class_a')
_middleware.set_return('class_b')
_middleware.set_return('class_c')
_middleware.set_return('class_d')

for key, value in _middleware.iterresults():
    print key, value

print _middleware.get_return('class_b')

for name in _middleware.iterkeys():
    print name

print 'test pipe success'

if  _middleware.pipe_success('class_b'):
    raise

_middleware.set_return('class_a', common.EXECUTE_SUCCESS)
_middleware.set_return('class_b', common.EXECUTE_SUCCESS)
_middleware.set_return('class_c', common.EXECUTE_SUCCESS)

if  not _middleware.pipe_success('class_c'):
    raise

print 'all test success'
