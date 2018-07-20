# -*- coding:utf-8 -*-
import six
import abc

from simpleutil.utils import jsonutils


@six.add_metaclass(abc.ABCMeta)
class BaseCondition(object):
    CONDITIONS = {'type': 'object',
                  'required': ['operator', 'value'],
                  'properties': {
                      'operator': {'enum': ['>', '=', '<', '!='],
                                   'description': '匹配数量比较方法'},
                      'value': {'type': 'integer', 'description': '操作匹配值'},
                      'counter': {'enum': ['>', '=', '<', '!='],
                                  'description': '匹配数量比较方法'},
                      'count': {'type': 'integer', 'description': '匹配数量'},
                      'all': {'type': 'boolean', 'description': '必须全部匹配'}}
                  }

    def __init__(self, position, kwargs):
        self.kwargs = self._kwarg_check(kwargs)
        self.position = position

    @abc.abstractmethod
    def _kwarg_check(self, kwargs):
        jsonutils.schema_validate(kwargs, self.CONDITIONS)
        return kwargs

    def check(self, *args, **kwargs):
        mothed = getattr(self, self.__getattribute__('%s_run' % self.position))
        return mothed(*args, **kwargs)

    @abc.abstractmethod
    def pre_run(self, asyncrequest, wait_agents):
        raise NotImplementedError

    @abc.abstractmethod
    def after_run(self, asyncrequest, wait_agents):
        raise NotImplementedError

    @abc.abstractmethod
    def post_run(self, asyncrequest, no_response_agents):
        raise NotImplementedError
