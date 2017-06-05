import webob.exc

from sqlalchemy.sql import or_
from sqlalchemy.sql import and_

from simpleutil.utils import argutils

from simpleutil.common.exceptions import InvalidArgument

from simpleservice.ormdb.api import model_query
from simpleservice.ormdb.api import model_count_with_key

from goperation.plugin.manager import common as manager_common
from goperation.plugin.manager.api import get_session
from goperation.plugin.manager.models import WsgiRequest
from goperation.plugin.manager.wsgi import resultutils
from goperation.plugin.manager.wsgi import contorller


FAULT_MAP = {InvalidArgument: webob.exc.HTTPClientError}

MAX_ROW_PER_REQUEST = 100


class AsyncWorkRequest(contorller.BaseContorller):

    def index(self, req, body):
        session = get_session(readonly=True)
        order = body.get('order', None)
        desc = body.get('desc', False)
        status = body.get('status', 1)
        if status not in (0, 1):
            raise InvalidArgument('Status value error, not 0 or 1')
        # index in request_time
        # so first filter is request_time
        filter_list = []
        start_time = int(body.get('start_time', 0))
        end_time = int(body.get('start_time', 0))
        if start_time:
            filter_list.append(WsgiRequest.request_time >= start_time)
        if end_time:
            if end_time < start_time:
                raise InvalidArgument('end time less then start time')
            filter_list.append(WsgiRequest.request_time < end_time)
        filter_list.append(WsgiRequest.status == status)
        sync = body.get('sync', True)
        async = body.get('async', True)
        if not sync and async:
            raise InvalidArgument('No both sync and async mark')
        if sync and not async:
            filter_list.append(WsgiRequest.async_checker == 0)
        elif async and not sync:
            filter_list.append(WsgiRequest.async_checker != 0)
        request_filter = and_(*filter_list)
        ret_dict = resultutils.bulk_results(session,
                                            model=WsgiRequest,
                                            columns=[WsgiRequest.request_id,
                                                     WsgiRequest.status,
                                                     WsgiRequest.request_time,
                                                     WsgiRequest.async_checker,
                                                     WsgiRequest.result
                                                     ],
                                            counter=WsgiRequest.request_id,
                                            order=order, desc=desc,
                                            filter=request_filter)
        return ret_dict

    @argutils.Idformater(key='request_id')
    def show(self, req, request_id, body):
        if len(request_id) != 1:
            raise InvalidArgument('Request show just for one request')
        request_id = request_id.pop()
        session = get_session(readonly=True)
        query = model_query(session, WsgiRequest)
        request = query.filter_by(request_id=request_id).first()
        if not request:
            raise InvalidArgument('Request id:%s can not be found' % request_id)
        agents = body.get('agents', True)
        details = body.get('details', False)
        return resultutils.request(request, agents, details)

    @argutils.Idformater(key='request_id')
    def update(self, req, request_id, body):
        """For scheduler update row of
        async_checker,deadline, and status and result"""
        if len(request_id) != 1:
            raise InvalidArgument('Request update just for one request')
        request_id = request_id.pop()
        async_checker = int(body.get('async_checker', 0))
        if async_checker <= 0:
            raise InvalidArgument('Async checker id is 0')
        data = {'async_checker': async_checker}
        session = get_session()
        with session.begin(subtransactions=True):
            query = model_query(session, WsgiRequest,
                                filter=or_(WsgiRequest.async_checker == 0,
                                           WsgiRequest.async_checker == async_checker))
            unfinish_request = query.filter_by(request_id=request_id,
                                               status=0).one_or_none()
            if not unfinish_request:
                raise InvalidArgument('Reuest is alreday finished or not exist')
            unfinish_request.async_checker = async_checker
            status = int(body.get('status', 0))
            if status not in (0, 1):
                raise InvalidArgument('Status value error, not 0 or 1')
            data['status'] = status
            deadline = int(body.get('deadline', 0))
            if deadline:
                if deadline < unfinish_request.deadline:
                    raise InvalidArgument('New deadline time can not small then old deadline time')
                if deadline - unfinish_request.deadline > 3600:
                    raise InvalidArgument('New deadline over old deleline time more then one hour')
                data['deadline'] = deadline
            result = body.get('result', None)
            if result:
                if len(result) > manager_common.MAX_REQUEST_RESULT:
                    raise InvalidArgument('Msg of request over range')
                unfinish_request.result = result
                data['result'] = result
            unfinish_request.update(data)
        return resultutils.request(unfinish_request)
