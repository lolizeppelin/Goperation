# -*- coding:utf-8 -*-

import requests

from simpleutil.utils import jsonutils

from goperation.manager.rpc.server import executer


class Executer(executer.BaseExecuter):
    # regex = re.compile(
    #     r'^(?:http)s?://' # http:// or https://
    #     r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|' #domain...
    #     r'localhost|' #localhost...
    #     r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})' # ...or ip
    #     r'(?::\d+)?' # optional port
    #     r'(?:/?|[/?]\S+)$', re.IGNORECASE)


    HTTPKWARGS = {'type': 'object',
                  'required': ['url'],
                  'properties': {
                      'url': {'type': 'string', 'format': 'uri', 'description': '请求url'},
                      'method': {'enum': ['GET', 'POST', 'DELETE', 'PUT', 'HEAD', 'OPTIONS']},
                      'params': {'type': 'object', 'description': 'url params参数'},
                      'data': {'type': 'object', 'description': 'url body数据'},
                      'timeout': {'type': 'integer', 'minimum': 3, 'description': '请求超时'}}
                  }

    def _check(self, kwargs):
        jsonutils.schema_validate(kwargs, self.HTTPKWARGS)
        kwargs = self.kwargs
        url = kwargs.pop('url')
        method = kwargs.pop('method', 'GET')
        params = kwargs.pop('params', None)
        data = kwargs.pop('data', None)
        timeout = kwargs.pop('timeout', 5)
        return dict(url=url, method=method, params=params, data=data, timeout=timeout)

    def execute(self):
        requests.request(**self.kwargs)
