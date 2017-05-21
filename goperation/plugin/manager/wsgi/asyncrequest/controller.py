import webob.exc

from sqlalchemy import func
from sqlalchemy.sql import or_

from simpleutil.utils import argutils

from simpleutil.common.exceptions import InvalidArgument

from simpleservice.ormdb.api import model_query

from goperation.plugin.manager import common as manager_common
from goperation.plugin.manager.dbapi import get_session
from goperation.plugin.manager.models import WsgiRequest
from goperation.plugin.manager.wsgi import resultutils
from goperation.plugin.manager.wsgi import contorller


FAULT_MAP = {InvalidArgument: webob.exc.HTTPClientError}

MAX_ROW_PER_REQUEST = 100


class AsyncWorkRequest(contorller.BaseContorller):

    def index(self, req, body):
        session = get_session(readonly=True)
        query = model_query(session, WsgiRequest)
        rows_num = session.query(func.count("*")).select_from(WsgiRequest).scalar()
        if rows_num >= manager_common.MAX_ROW_PER_REQUEST:
            query = query.limit(manager_common.MAX_ROW_PER_REQUEST)
        page_num = int(body.get('page', 0))
        if page_num and page_num*manager_common.ROW_PER_PAGE >= rows_num:
            raise InvalidArgument('Page number over size or no data exist')
        # index in request_time
        # so first filter is request_time
        start_time = int(body.get('start_time', 0))
        end_time = int(body.get('start_time', 0))
        if start_time:
            query = query.filter(WsgiRequest.request_time >= start_time)
        if end_time:
            query = query.filter(WsgiRequest.request_time < end_time)
        sync = body.get('sync', True)
        async = body.get('async', True)
        if not sync and async:
            raise InvalidArgument('No both sync and async mark')
        if sync and not async:
            query.filter(WsgiRequest.async_checker == 0)
        elif async and not sync:
            query = query.filter(WsgiRequest.async_checker != 0)
        if page_num:
            query.seek(page_num*manager_common.ROW_PER_PAGE)
        ret_dict = resultutils.requests(total=rows_num,
                                        pagenum=page_num,
                                        msg='Get request list success')
        for result in query:
            data = dict(request_id=result.request_id,
                        status=result.status,
                        request_time=result.request_time,
                        async_checker=result.async_checker,
                        result=result.result,
                        )
            ret_dict['data'].append(data)
        return ret_dict

    @argutils.Idformater(key='request_id', all_key=None)
    def show(self, req, request_id, body):
        session = get_session(readonly=True)
        query = model_query(session, WsgiRequest)
        request = query.filter_by(request_id=request_id).first()
        if not request:
            raise InvalidArgument('Request id:%s can not be found' % request_id)
        agents = body.get('agents', True)
        details = body.get('details', False)
        return resultutils.request(request, agents, details)

    def update(self, req, request_id, body):
        """For scheduler update row of
        async_checker,deadline, and status and result"""
        async_checker = int(body.get('async_checker'))
        if async_checker <= 0:
            raise InvalidArgument('Async checker id is zero')
        session = get_session(readonly=True)
        query = model_query(session, WsgiRequest).filter(or_(WsgiRequest.async_checker == 0,
                                                             WsgiRequest.async_checker == async_checker))
        with session.begin(subtransactions=True):
            unfinish_request = query.filter_by(request_id=request_id,
                                               status=0).first()
            if not unfinish_request:
                raise InvalidArgument('Reuest is alreday finished or not exist')
            unfinish_request.async_checker = async_checker
            status = int(body.get('status', None))
            if status:
                if status not in (0, 1):
                    raise InvalidArgument('Status value error, not 0 or 1')
                unfinish_request.status = status
            deadline = int(body.get('deadline', None))
            if deadline:
                if deadline < unfinish_request.deadline:
                    raise InvalidArgument('New deadline time can not small then old deadline time')
                if deadline - unfinish_request.deadline > 3600:
                    raise InvalidArgument('New deadline over old deleline time more then one hour')
                unfinish_request.deadline = deadline
            result = str(body.get('result', None))
            if result:
                if len(result) > manager_common.MAX_REQUEST_RESULT:
                    raise InvalidArgument('Msg of request over range')
                unfinish_request.result = result
            session.update(unfinish_request)
