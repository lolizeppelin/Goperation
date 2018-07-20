# -*- coding:utf-8 -*-
import six
import abc


@six.add_metaclass(abc.ABCMeta)
class BaseCondition(object):
    CONDITIONS = {'type': 'object',
                  'properties': {
                      'pre': {'type': 'object',
                              'required': ['operator', 'value', 'counter', 'count'],
                              'properties': {
                                  'operator': {'enum': ['>', '=', '<', '!='],
                                               'description': '匹配数量比较方法'},
                                  'value': {'type': 'integer', 'description': '操作匹配值'},
                                  'counter': {'enum': ['>', '=', '<', '!='],
                                              'description': '匹配数量比较方法'},
                                  'count': {'type': 'integer', 'description': '匹配数量'},
                                  'all': {'type': 'boolean', 'description': '必须全部匹配'},
                              }
                              },
                      'after': {'type': 'object',
                                'properties': {
                                    'required': ['operator', 'value', 'counter', 'count'],
                                    'operator': {'enum': ['>', '=', '<', '!='],
                                                 'description': '结果码比较方法'},
                                    'value': {'type': 'integer', 'description': '操作匹配值'},
                                    'counter': {'enum': ['>', '=', '<', '!=', 'all', 'none'],
                                                'description': '匹配数量比较方法'},
                                    'count': {'type': 'integer', 'description': '匹配数量'},
                                    'all': {'type': 'boolean', 'description': '必须全部匹配'},
                                }
                                },
                      'post': {'type': 'object',
                               'properties': {
                                   'required': ['operator', 'value', 'counter', 'count'],
                                   'operator': {'enum': ['>', '=', '<', '!='],
                                                'description': '结果码比较方法'},
                                   'value': {'type': 'integer', 'description': '操作匹配值'},
                                   'counter': {'enum': ['>', '=', '<', '!='],
                                               'description': '数量比较方法'},
                                   'count': {'type': 'integer', 'description': '匹配数量'},
                                   'all': {'type': 'boolean', 'description': '必须全部匹配'},
                               }
                               }}
                  }

    def __init__(self, kwargs):
        self.kwargs = kwargs

    @abc.abstractmethod
    def pre_run(self, asyncrequest, wait_agents):
        raise NotImplementedError

    @abc.abstractmethod
    def after_run(self, asyncrequest, wait_agents):
        raise NotImplementedError

    @abc.abstractmethod
    def post_run(self, asyncrequest, no_response_agents):
        raise NotImplementedError
