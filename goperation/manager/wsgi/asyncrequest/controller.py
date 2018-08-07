# -*- coding:utf-8 -*-
import time
import webob.exc
from sqlalchemy.sql import and_
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.orm.exc import MultipleResultsFound

from simpleutil.log import log as logging
from simpleutil.utils import argutils
from simpleutil.utils import jsonutils
from simpleutil.utils import singleton

from simpleservice.ormdb.api import model_query
from simpleutil.common.exceptions import InvalidArgument

from goperation import threadpool
from goperation.manager.utils import resultutils
from goperation.manager.utils import responeutils
from goperation.manager import common as manager_common
from goperation.manager.api import get_cache
from goperation.manager.api import get_session
from goperation.manager.models import AgentRespone
from goperation.manager.models import AsyncRequest
from goperation.manager.wsgi import contorller

LOG = logging.getLogger(__name__)

FAULT_MAP = {InvalidArgument: webob.exc.HTTPClientError,
             NoResultFound: webob.exc.HTTPNotFound,
             MultipleResultsFound: webob.exc.HTTPInternalServerError}


Idformater = argutils.Idformater(key='request_id', formatfunc='request_id_check')


INDEXSCHEMA = {
    'type': 'object',
    'properties':
        {
             'order': {'type': 'string'},                                     # short column name
             'desc': {'type': 'boolean'},                                     # reverse result
             'start': {'type': 'string', 'format': 'date-time'},              # request start time
             'end': {'type': 'string', 'format': 'date-time'},                # request end time
             'page_num': {'type': 'integer', 'minimum': 0},                   # pagen number
             'status': {'type': 'integer',                                    # filter status
                        'enum': [manager_common.ACTIVE, manager_common.UNACTIVE]},
         }
}


OVERTIMESCHEMA = {
     'type': 'object',
     'required': ['agent_time', 'agents'],
     'properties': {
             'agent_time': {'type': 'integer', 'minimum': 0},               # respone time
             'agents':  {'type': 'array', 'minItems': 1,                    # overtime agents list
                         'items': {'type': 'integer', 'minimum': 0}}
         }
}


@singleton.singleton
class AsyncWorkRequest(contorller.BaseContorller):

    def index(self, req, body=None):
        body = body or {}
        jsonutils.schema_validate(body, INDEXSCHEMA)
        session = get_session(readonly=True)
        order = body.get('order', None)
        desc = body.get('desc', False)
        status = body.get('status', None)
        page_num = body.pop('page_num', 0)
        filter_list = []
        start = int(body.get('start', 0))
        end = int(body.get('end', 0))
        if start:
            filter_list.append(AsyncRequest.request_time >= end)
        if end:
            if end < start:
                raise InvalidArgument('end time less then start time')
            filter_list.append(AsyncRequest.request_time < end)
        if status is not None:
            filter_list.append(AsyncRequest.status == status)
        request_filter = and_(*filter_list)
        return resultutils.bulk_results(session,
                                        model=AsyncRequest,
                                        columns=[AsyncRequest.request_id,
                                                 AsyncRequest.resultcode,
                                                 AsyncRequest.status,
                                                 AsyncRequest.request_time,
                                                 AsyncRequest.finishtime,
                                                 AsyncRequest.deadline,
                                                 AsyncRequest.expire,
                                                 ],
                                        counter=AsyncRequest.request_id,
                                        order=order, desc=desc,
                                        filter=request_filter, page_num=page_num, limit=200)

    @Idformater
    def show(self, req, request_id, body=None):
        body = body or {}
        agents = body.get('agents', True)
        details = body.get('details', False)
        session = get_session(readonly=True)
        query = model_query(session, AsyncRequest, filter=AsyncRequest.request_id == request_id)
        if agents:
            joins = joinedload(AsyncRequest.respones)
            if details:
                joins = joins.joinedload(AgentRespone.details)
            query = query.options(joins)
        request = query.one()
        async_result = resultutils.async_request(request, agents, details)
        return resultutils.results(result='show async request success', data=[async_result])

    @Idformater
    def update(self, req, request_id, body=None):
        raise NotImplementedError('update asynecrequest not implemented')

    @Idformater
    def response(self, req, request_id, body):
        """agent report respone api"""
        session = get_session()
        asyncrequest = model_query(session, AsyncRequest, filter=AsyncRequest.request_id == request_id).one()
        if not asyncrequest.expire:
            return responeutils.agentrespone(session, request_id, body)
        else:
            return responeutils.agentrespone(get_cache(), request_id, body)

    @Idformater
    def overtime(self, req, request_id, body):
        """
        agent not response, async checker send a overtime respone
        此接口为保留接口,接口功能已经在rpc server中实现
        """
        jsonutils.schema_validate(body, OVERTIMESCHEMA)
        agent_time = body.get('agent_time')
        agents = set(body.get('agents'))
        session = get_session()
        query = model_query(session, AsyncRequest).filter_by(request_id=request_id)
        asynecrequest = query.one()
        if asynecrequest.status == manager_common.FINISH:
            raise InvalidArgument('Async request has been finished')

        def bluk():
            bulk_data = []
            for agent_id in agents:
                data = dict(request_id=request_id,
                            agent_id=agent_id,
                            agent_time=agent_time,
                            server_time=int(time.time()),
                            resultcode=manager_common.RESULT_OVER_FINISHTIME,
                            result='Agent respone overtime')
                bulk_data.append(data)
            responeutils.bluk_insert(storage=get_cache() if asynecrequest.expire else session,
                                     agents=agents, bulk_data=bulk_data, expire=asynecrequest.expire)

            if agents:
                query.update({'status': manager_common.FINISH,
                              'resultcode': manager_common.RESULT_NOT_ALL_SUCCESS,
                              'result': '%d agent not respone' % len(agents)})
            else:
                query.update({'status': manager_common.FINISH,
                              'resultcode': manager_common.RESULT_SUCCESS,
                              'result': 'all agent respone result' % len(agents)})
            session.flush()
            session.close()

        threadpool.add_thread(bluk)
        return resultutils.results(result='Post agent overtime success')
