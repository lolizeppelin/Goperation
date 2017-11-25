import webob.exc
from sqlalchemy.sql import and_
from sqlalchemy.sql import or_
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.orm.exc import MultipleResultsFound

from redis.exceptions import RedisError

from simpleutil.log import log as logging
from simpleutil.utils import argutils
from simpleutil.utils import jsonutils
from simpleutil.utils import singleton

from simpleservice.ormdb.api import model_query
from simpleservice.ormdb.exceptions import DBDuplicateEntry
from simpleservice.ormdb.exceptions import DBError
from simpleutil.common.exceptions import InvalidArgument

from goperation import threadpool
from goperation.manager.utils import resultutils
from goperation.manager.utils import targetutils
from goperation.manager.utils import responeutils
from goperation.manager import common as manager_common
from goperation.manager.api import get_cache
from goperation.manager.api import get_session
from goperation.manager.models import AgentRespone
from goperation.manager.models import AsyncRequest
from goperation.manager.models import ResponeDetail
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
          'desc': {'type': 'boolean'},                                        # reverse result
          'start': {'type': 'string', 'format': 'date-time'},              # request start time
          'end': {'type': 'string', 'format': 'date-time'},                # request end time
          'page_num': {'type': 'integer', 'minimum': 0},                   # pagen number
          'status': {'enum': [manager_common.ACTIVE,                       # filter status
                              manager_common.UNACTIVE]},
          }
}

OVERTIMESCHEMA = {
     'type': 'object',
     'required': ['agent_time', 'agents'],
     'properties':
         {
          'agent_time': {'type': 'integer', 'minimum': 0},                                 # scheduler respone time
          'agents':  {'type': 'array', 'minItems': 1,
                      'items': {'type': 'integer', 'minimum': 0}}                          # overtime agents list
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
                                                 AsyncRequest.scheduler,
                                                 ],
                                        counter=AsyncRequest.request_id,
                                        order=order, desc=desc,
                                        filter=request_filter, page_num=page_num)

    @Idformater
    def show(self, req, request_id, body=None):
        body = body or {}
        agents = body.get('agents', True)
        details = body.get('details', False)
        session = get_session(readonly=True)
        query = model_query(session, AsyncRequest)
        request = query.filter_by(request_id=request_id).one()
        if not request.expire:
            # get response from database
            return resultutils.async_request(request, agents, details)
        else:
            ret_dict = resultutils.async_request(request,
                                                 agents=False, details=False)
            cache_store = get_cache()
            # get respone from cache redis server
            key_pattern = targetutils.async_request_pattern(request_id)
            respone_keys = cache_store.keys(key_pattern)
            agent_respones = cache_store.mget(respone_keys)
            if agent_respones:
                for agent_respone in agent_respones:
                    if agent_respone:
                        try:
                            agent_respone_data = jsonutils.loads_as_bytes(agent_respone)
                        except (TypeError, ValueError):
                            continue
                        ret_dict['respones'].append(agent_respone_data)
            return ret_dict

    @Idformater
    def update(self, req, request_id, body=None):
        raise NotImplementedError('update asynecrequest not implemented')

    @Idformater
    def respone(self, req, request_id, body):
        """agent report respone api"""
        session = get_session()
        asyncrequest = model_query(session, AsyncRequest, filter=AsyncRequest.request_id == request_id).one()
        if not asyncrequest.expire:
            return responeutils.agentrespone(session, request_id, body)
        else:
            return responeutils.agentrespone(get_cache(), request_id, body)

    @Idformater
    def responses(self, req, request_id, body):
        """Find agents not witch not respone"""
        agents = argutils.map_to_int(body.pop('agents'))
        session = get_session(readonly=True)
        # esure request_id
        asyncrequest = model_query(session, AsyncRequest, filter=AsyncRequest.request_id == request_id).one()
        if not asyncrequest.expire:
            wait_agents = responeutils.norespones(session, request_id, agents)
        else:
            wait_agents = responeutils.norespones(get_cache(), request_id, agents)
        return resultutils.results(result='Get agents success', data=[dict(agents=list(wait_agents))])

    @Idformater
    def details(self, req, request_id, body):
        try:
            agent_id = int(body.get('agent_id'))
        except (KeyError, TypeError):
            raise InvalidArgument('Get agent respone need agent_id value of int')
        session = get_session(readonly=True)
        agent_filter = and_(ResponeDetail.request_id == request_id,
                            ResponeDetail.agent_id == agent_id)
        query = model_query(session, ResponeDetail, filter=agent_filter)
        details = query.all()
        if not details:
            return resultutils.results(result='Details of agent %d can not be found' % agent_id,
                                       resultcode=manager_common.RESULT_IS_NONE)
        return resultutils.results(result='Get details success',
                                   data=[resultutils.detail(detail) for detail in details])

    @Idformater
    def overtime(self, req, request_id, body):
        """agent not response, async checker send a overtime respone"""
        jsonutils.schema_validate(OVERTIMESCHEMA, body)
        agent_time = body.get('agent_time')
        agents = body.get('agents')
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
                            resultcode=manager_common.RESULT_OVER_FINISHTIME,
                            result='Agent respone overtime')
                bulk_data.append(data)
            count = responeutils.bluk_insert(storage=get_cache() if asynecrequest.expire else session,
                                              bulk_data=bulk_data, expire=asynecrequest.expire)

            if count:
                query.update({'status': manager_common.FINISH,
                              'resultcode': manager_common.RESULT_NOT_ALL_SUCCESS,
                              'result': '%d agent not respone' % count})
            else:
              query.update({'status': manager_common.FINISH,
                             'resultcode': manager_common.RESULT_SUCCESS,
                             'result': 'all agent respone result' % count})
            session.commit()
            session.close()

        threadpool.add_thread(bluk)
        return resultutils.results(result='Post agent overtime success')
