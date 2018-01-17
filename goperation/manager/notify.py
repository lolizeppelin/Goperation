import six
import abc
import inspect

from simpleutil.utils import jsonutils
from simpleservice.rpc.target import Target

from goperation.manager.api import get_http
from goperation.manager.api import get_client

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
             'body': {'type': 'object'},
             'headers': {'type': 'object'},
             'params': {'type': 'object'},
             'timeout': {'type': 'integer', 'minimum': 3, 'maxmum': 30}}
         }
    ]
}


@six.add_metaclass(abc.ABCMeta)
class NotifyInterface(object):
    def __init__(self, notify):
        self.notify = notify

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
    @abc.abstractmethod
    def success(self):
        """when success"""

    @abc.abstractmethod
    def fail(self):
        """when fail"""


class RpcNotify(NotifyInterface, GeneralNotify):
    def default(self):
        raise NotImplementedError

    def success(self):
        key = inspect.stack()[0][3]
        if key not in self.notify:
            return
        data = self.notify[key]
        target = Target(**data.pop('target'))
        func = getattr(get_client(), data.pop('method'))
        func(target, **data)

    def fail(self):
        key = inspect.stack()[0][3]
        if key not in self.notify:
            return
        data = self.notify[key]
        target = Target(**data.pop('target'))
        func = getattr(get_client(), data.pop('method'))
        func(target, **data)


class HttpNotify(NotifyInterface, GeneralNotify):
    def default(self):
        raise NotImplementedError

    def success(self):
        key = inspect.stack()[0][3]
        if key not in self.notify:
            return
        data = self.notify[key]
        func = getattr(get_http(), 'do_request')
        func(**data)

    def fail(self):
        key = inspect.stack()[0][3]
        if key not in self.notify:
            return
        data = self.notify[key]
        func = getattr(get_http(), 'do_request')
        func(**data)


def notify_prepare(notify):
    if not notify:
        return EmptyNotify(notify)
    notifys = set()
    for data in six.itervalues(notify):
        jsonutils.schema_validate(data, NOTIFYSCHEMA)
        if 'target' in data:
            notifys.add(RpcNotify)
        if 'action' in data:
            notifys.add(HttpNotify)
    if len(notifys) != 1:
        notifys.clear()
        raise ValueError('Notify type error!')
    cls = notifys.pop()
    for attrib in notify:
        if not hasattr(cls, attrib):
            raise AttributeError('Notify has no %s' % attrib)
    return cls(notify)
