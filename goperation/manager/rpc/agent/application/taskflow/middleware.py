import six
import collections

from goperation.taskflow import common
from goperation.manager.rpc.agent.application.base import AppEndpointBase


class EntityMiddleware(object):

    def __init__(self, entity, endpoint):
        if not isinstance(endpoint, AppEndpointBase):
            raise RuntimeError('endpoint not AppEndpointBase')
        self.entity = entity
        self._endpoint = endpoint
        self.results = collections.OrderedDict()
        self.errors = []
        self.dberrors = []
        self._exclude = None

    @property
    def entity_home(self):
        return self._endpoint.entity_home(self.entity)

    @property
    def apppath(self):
        return self._endpoint.apppath(self.entity)

    @property
    def entity_user(self):
        return self._endpoint.entity_user(self.entity)

    @property
    def entity_group(self):
        return self._endpoint.entity_group(self.entity)

    @property
    def endpoint(self):
        return self._endpoint.namespace

    @property
    def filemanager(self):
        return self._endpoint.filemanager

    def reflection(self):
        return self._endpoint

    def set_return(self, name, result=common.NOT_EXECUTED):
        self.results[name] = result

    def get_return(self, name):
        return self.results[name]

    def is_success(self, name):
        result = self.results[name]
        if result is common.EXECUTE_SUCCESS:
            return True
        return False

    def pipe_success(self, name):
        for key, value in self.iterresults():
            if value is not common.EXECUTE_SUCCESS:
                return False
            if key == name:
                break
        return True

    @property
    def success(self):
        for value in self.itervalues():
            if value is not common.EXECUTE_SUCCESS:
                return False
        return True

    def _exclude(self, x):
        return True

    @property
    def exclude(self):
        return self._exclude

    def iterresults(self):
        return six.iteritems(self.results)

    def iterkeys(self):
        return six.iterkeys(self.results)

    def itervalues(self):
        return six.itervalues(self.results)

    def __str__(self):
        return ','.join(['%s:%s' % (k, v) for k, v in self.iterresults()])
