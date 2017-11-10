from simpleutil.utils import importutils
from simpleutil.utils import reflection

from goperation.taskflow import common
from goperation.manager import common as manager_common


class SchedulerTaskBase(object):

    ECLS = object
    RCLS = object

    @classmethod
    def esure_subclass(cls, step):
        if step.get('execute'):
            ecls = importutils.import_class(step.get('execute'))
            if not reflection.is_subclass(ecls, cls.ECLS):
                raise TypeError('Scheduler execute is enable subclass of %s' % cls.__name__)
        if step.get('revert'):
            rcls =  importutils.import_class(step.get('revert'))
            if not reflection.is_subclass(rcls, cls.RCLS):
                raise TypeError('Scheduler revert is enable subclass of %s' % cls.__name__)

    def post_execute(self):
        self.jobstep.resultcode = manager_common.RESULT_SUCCESS
        self.jobstep.result = common.EXECUTE_SUCCESS


    @classmethod
    def builder(cls, name, jobstep, **kwargs):
        raise NotImplementedError('builder not implemented')
