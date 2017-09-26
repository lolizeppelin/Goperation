from goperation.taskflow import common
from goperation.manager.rpc.agent.application.taskflow import middleware
from test.unit.taskflow import test_group
from test.unit.taskflow import TestEndpoint
from test.unit.taskflow import TestManager


mananager = TestManager('/root')

endpoint = TestEndpoint(manager=mananager, group=test_group)

_middleware = middleware.EntityMiddleware(entity=1, endpoint=endpoint)


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
