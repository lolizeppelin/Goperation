import six
import copy
import abc
import requests
import inspect

from simpleutil.log import log as logging
from simpleutil.utils import jsonutils
from simpleservice.rpc.target import Target

import goperation
from goperation.utils import safe_func_wrapper
from goperation.manager.api import get_http
from goperation.manager.api import get_client

LOG = logging.getLogger(__name__)

NOTIFYSCHEMA = {
    'oneOf': [
        {'type': 'object',
         'required': ['method', 'target', 'ctxt', 'msg'],
         'properties': {
             'target': {'type': 'object',
                        'required': ['topic', 'namespace'],
                        'properties': {
                            'exchange': {'oneOf': [{'type': 'null'}, {'type': 'string'}]},
                            'topic': {'type': 'string'},
                            'namespace': {'oneOf': [{'type': 'null'}, {'type': 'string'}]},
                            'version': {'type': 'string'},
                            'server': {'oneOf': [{'type': 'null'}, {'type': 'string'}]},
                            'fanout': {'oneOf': [{'type': 'null'}, {'type': 'string'}]}}
                        },
             'method': {'type': 'string', 'enum': ['cast', 'call', 'notify']},
             'ctxt': {'type': 'object'},
             'msg': {'type': 'object'},
             'timeout': {'type': 'integer', 'minimum': 5}}
         },
        {'type': 'object',
         'required': ['method', 'action'],
         'properties': {
             'method': {'type': 'string',
                        'enum': ['GET', 'DELETE', 'POST', 'PUT', 'HEAD', 'PATCH', 'OPTIONS']},
             'action': {'type': 'string'},
             'body': {'oneOf': [{'type': 'null'}, {'type': 'object'}]},
             'headers': {'oneOf': [{'type': 'null'}, {'type': 'object'}]},
             'params': {'oneOf': [{'type': 'null'}, {'type': 'object'}]},
             'timeout': {'oneOf': [{'type': 'null'}, {'type': 'integer', 'minimum': 3, 'maxmum': 30}]}}
         },
        {'type': 'object',
         'required': ['method', 'url'],
         'properties': {
             'method': {'type': 'string',
                        'enum': ['GET', 'DELETE', 'POST', 'PUT', 'HEAD', 'PATCH', 'OPTIONS']},
             'url': {'type': 'string'},
             'data': {'oneOf': [{'type': 'null'}, {'type': 'object'}]},
             'json': {'oneOf': [{'type': 'null'}, {'type': 'object'}]},
             'headers': {'oneOf': [{'type': 'null'}, {'type': 'object'}]},
             'params': {'oneOf': [{'type': 'null'}, {'type': 'object'}]},
             'timeout': {'oneOf': [{'type': 'null'}, {'type': 'integer', 'minimum': 3, 'maxmum': 30}]}}
         }
    ]
}


@six.add_metaclass(abc.ABCMeta)
class NotifyInterface(object):

    def __init__(self, notify):
        self.notify = notify

    @abc.abstractmethod
    def _do(self, keyword, replace=None):
        """impl do"""

    @abc.abstractmethod
    def default(self, *args, **kwargs):
        """"""

    def __getattr__(self, attrib):
        return self.default


class EmptyNotify(NotifyInterface):

    def default(self):
        """do nothing"""


@six.add_metaclass(abc.ABCMeta)
class GeneralNotify(object):

    def success(self):
        key = inspect.stack()[0][3]
        self._do(key)

    def fail(self):
        keyword = inspect.stack()[0][3]
        self._do(keyword)


class GopRpcNotify(NotifyInterface, GeneralNotify):

    def default(self):
        raise NotImplementedError

    def _do(self, keyword, replace=None):
        if keyword not in self.notify:
            return

        def wapper():
            data = self.notify[keyword]
            target = Target(**data.pop('target'))
            func = getattr(get_client(), data.pop('method'))
            func(target, **data)

        goperation.threadpool.add_thread(safe_func_wrapper, wapper, LOG)


class GopHttpNotify(NotifyInterface, GeneralNotify):

    def default(self):
        raise NotImplementedError

    def _do(self, keyword, replace=None):
        LOG.debug('Notify %s called' % keyword)
        if keyword not in self.notify:
            return

        def wapper():
            data = self.notify[keyword]
            func = getattr(get_http(), 'do_request')
            func(**data)

        goperation.threadpool.add_thread(safe_func_wrapper, wapper, LOG)


class HttpNotify(NotifyInterface):
    def default(self):
        raise NotImplementedError

    def _do(self, keyword, replace=None):
        LOG.debug('Notify %s called' % keyword)
        if keyword not in self.notify:
            return

        def wapper():
            data = self.notify[keyword]
            if replace:
                data = copy.deepcopy(data)
                data.update(replace)
            requests.request(**data)

        goperation.threadpool.add_thread(safe_func_wrapper, wapper, LOG)


def notify_prepare(notify):
    if not notify:
        return EmptyNotify(notify)
    notifys = set()
    for data in six.itervalues(notify):
        jsonutils.schema_validate(data, NOTIFYSCHEMA)
        if 'target' in data:
            notifys.add(GopRpcNotify)
        if 'action' in data:
            notifys.add(GopHttpNotify)
        if 'url' in data:
            notifys.add(HttpNotify)
    if len(notifys) != 1:
        notifys.clear()
        raise ValueError('Notify type error, more then one')
    cls = notifys.pop()
    for attrib in notify:
        if not hasattr(cls, attrib):
            raise AttributeError('Notify has no %s' % attrib)
    LOG.info('Prepare notify %s' % cls.__name__)
    return cls(notify)
