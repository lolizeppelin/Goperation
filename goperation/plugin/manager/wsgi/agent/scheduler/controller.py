import webob.exc

from simpleutil.common.exceptions import InvalidArgument

from simpleutil.utils.argutils import Idformater


FAULT_MAP = {InvalidArgument: webob.exc.HTTPClientError}


class SchedulerRequest(object):

    def __init__(self):
        self._all_server_id = set()

    def index(self, req, body):
        return 'index'

    def show(self, req, request_id, body):
        return 'show'
