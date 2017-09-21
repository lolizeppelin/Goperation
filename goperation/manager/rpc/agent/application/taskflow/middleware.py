import six
import collections

from goperation.taskflow import common


class EntityMiddleware(object):

    def __init__(self, endpoint, entity,
                 application=None, databases=None):
        self.entity = entity
        self.entity_home = endpoint.entity_home(entity)
        self.entity_appname = endpoint.appname(entity)
        self.entity_user = endpoint.entity_user(entity)
        self.entity_group = endpoint.entity_group(entity)
        self.endpoint = endpoint.namespace
        self.filemanager = endpoint.filemanager
        self.application = application
        self.databases = databases
        self.results = collections.OrderedDict()

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
            if key == name:
                break
            if value is not common.EXECUTE_SUCCESS:
                return False
        return True

    def iterresults(self):
        return six.iteritems(self.results)

    def iterkeys(self):
        return six.iterkeys(self.results)
