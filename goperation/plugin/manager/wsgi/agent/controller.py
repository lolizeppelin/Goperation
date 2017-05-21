import webob.exc

from simpleutil.utils.argutils import Idformater
from simpleutil.common.exceptions import InvalidArgument

from goperation.plugin.manager.dbapi import get_session

FAULT_MAP = {InvalidArgument: webob.exc.HTTPClientError}


class AsyncWorkRequest(object):

    def __init__(self):
        self._all_server_id = set()

    def index(self, req, body):
        return 'index'

    @Idformater(key='request_id', all_key=None)
    def show(self, req, request_id, body):
        return 'show'


    def create(self, req, body):
        session = get_session(readonly=True)
        new_request = WsgiRequest()
        session.add(new_request)
        session.flush()
        data = dict(request_id=new_request.request_id,
                    status=new_request.status,
                    request_time=new_request.request_time,
                    async_checker=new_request.async_checker,
                    result=new_request.result,
                    )
        ret_dict = {'total':1, 'data':[data, ], 'msg':'Create request success'}
        return ret_dict