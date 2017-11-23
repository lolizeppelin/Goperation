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
from goperation.manager import resultutils
from goperation.manager import targetutils
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

RESPONESCHEMA = {
     'type': 'object',
     'required': ['agent_id', 'agent_time', 'resultcode', 'persist'],
     'properties':
         {
          'agent_id': {'type': 'integer', 'minimum': 0},                                   # agent id
          'agent_time': {'type': 'integer', 'minimum': 0},                                 # agent respone time
          'resultcode': {'type': 'integer', 'minimum': -127, 'maxmum': 127},               # resultcode
          'result': {'type': 'string'},                                                    # result message
          'persist': {'type': 'boolean'},                                                  # persist
          'expire': {'type': 'integer', 'minimum': 10},                                    # when persist is false
          'details': {'type': 'array', 'minItems': 1,                                      # details for rpc
                      'items': {'type': 'object',
                                'required': ['detail_id', 'resultcode', 'result'],
                                'properties': {
                                    'detail_id': {'type': 'integer', 'minimum': 0},
                                    'resultcode': {'type': 'integer', 'minimum': -127, 'maxmum': 127},
                                    'result': [{'type': 'string'}, {'type': 'object'}]}
                                }
                      }
         }
}

OVERTIMESCHEMA = {
     'type': 'object',
     'required': ['scheduler', 'agent_time', 'agents', 'persist'],
     'properties':
         {
          'scheduler': {'type': 'integer', 'minimum': 0},                                  # scheduler agent id
          'agent_time': {'type': 'integer', 'minimum': 0},                                 # scheduler respone time
          'agents':  {'type': 'array', 'minItems': 1,
                      'items': {'type': 'integer', 'minimum': 0}},                         # overtime agents list
          'persist': {'type': 'boolean'},                                                  # persist
          'expire': {'type': 'integer', 'minimum': 10},                                    # when persist is false
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
        if request.persist:
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
        jsonutils.schema_validate(RESPONESCHEMA, body)
        agent_id = body.get('agent_id')
        agent_time = body.get('agent_time')
        resultcode = body.get('resultcode')
        result = body.get('result', 'no result message')
        persist = body.get('persist', 1)
        expire = body.get('expire', 60)
        details = [dict(agent_id=agent_id,
                        request_id=request_id,
                        detail_id=detail['detail'],
                        resultcode=detail['resultcode'],
                        result=detail['result'] if isinstance(detail['result'], basestring)
                        else jsonutils.dumps_as_bytes(detail['result'])) for detail in body.get('details', [])]
        cache_store = get_cache()
        session = get_session()
        data = dict(request_id=request_id,
                    agent_id=agent_id,
                    agent_time=agent_time,
                    resultcode=resultcode,
                    result=result,
                    )
        if persist:
            try:
                with session.begin():
                    session.add(AgentRespone(**data))
                    session.flush()
                    for detail in details:
                        session.add(ResponeDetail(**detail))
                        session.flush()
            except DBDuplicateEntry:
                LOG.warning('Agent %d respone %s get DBDuplicateEntry error' % (agent_id, request_id))
                query = model_query(session, AgentRespone,
                                    filter=and_(AgentRespone.request_id == request_id,
                                                AgentRespone.agent_id == agent_id))
                with session.begin(subtransactions=True):
                    respone = query.one()
                    if respone.resultcode != manager_common.RESULT_OVER_FINISHTIME:
                        result = 'Agent %d respone %s fail,another agent with same agent_id in database' % \
                                 (agent_id, request_id)
                        LOG.error(result)
                        return resultutils.results(result=result,
                                                   resultcode=manager_common.RESULT_ERROR)
                    query.update(data)
        else:
            data.setdefault('details', details)
            respone_key = targetutils.async_request_key(request_id, agent_id)
            try:
                if not cache_store.set(respone_key, jsonutils.dumps_as_bytes(data), ex=expire, nx=True):
                    LOG.warning('Scheduler set agent overtime to redis get a Duplicate Entry, Agent responed?')
                    respone = jsonutils.loads_as_bytes(cache_store.get(respone_key))
                    if respone.get('resultcode') != manager_common.RESULT_OVER_FINISHTIME:
                        result = 'Agent %d respone %s fail,another agent ' \
                                 'with same agent_id in redis' % (agent_id, request_id)
                        LOG.error(result)
                        return resultutils.results(result=result, resultcode=manager_common.RESULT_ERROR)
                    # overwirte respone_key
                    cache_store.set(respone_key, jsonutils.dumps_as_bytes(data), ex=expire, nx=False)
            except RedisError as e:
                LOG.error('Scheduler set agent overtime to redis get RedisError %s: %s' % (e.__class__.__name__,
                                                                                           e.message))
                result = 'Agent %d respne %s fail, write to redis fail' % \
                         (agent_id, request_id)
                return resultutils.results(result=result,
                                           resultcode=manager_common.RESULT_ERROR)
        return resultutils.results(result='Agent %d Post respone of %s success' % (agent_id, request_id))

    @Idformater
    def responses(self, req, request_id, body):
        """Find agents not witch not respone"""
        persist = body.pop('persist', True)
        agents = argutils.map_to_int(body.pop('agents'))
        session = get_session(readonly=True)
        response_agents = set()
        if persist:
            query = model_query(session, AgentRespone.agent_id, filter=AgentRespone.request_id == request_id)
            # get response from database
            for r in query.all():
                response_agents.add(r[0])
        else:
            model_query(session, AsyncRequest, filter=AgentRespone.request_id == request_id).one()
            cache_store = get_cache()
            # get respone from cache redis server
            key_pattern = targetutils.async_request_pattern(request_id)
            respone_keys = cache_store.keys(key_pattern)
            for key in respone_keys:
                response_agents.add(int(key.split('-')[-1]))
        wait_agents = set(agents) - response_agents
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
        scheduler = body.get('scheduler')
        agent_time = body.get('agent_time')
        agents = body.get('agents')
        persist = body.get('persist')
        expire = body.get('expire', 60)
        bulk_data = []
        for agent_id in agents:
            data = dict(request_id=request_id,
                        agent_id=agent_id,
                        agent_time=agent_time,
                        resultcode=manager_common.RESULT_OVER_FINISHTIME,
                        result='Agent respone overtime, report by Scheduler:%d' % scheduler)
            bulk_data.append(data)
        # self.bluk_insert(bulk_data, persist, expire)
        threadpool.add_thread(self.bluk_insert, bulk_data, persist, expire)
        return resultutils.results(result='Scheduler post agent overtime success')

    @staticmethod
    def bluk_insert(bulk_data, persist, expire):
        session = get_session()
        request_id = bulk_data[0]['request_id']
        agent_id = bulk_data[0]['agent_id']
        count_finish = 0
        query = model_query(session, AsyncRequest).filter_by(request_id=request_id)
        asynecrequest = query.one()
        if asynecrequest.status == manager_common.FINISH:
            return
        if persist:
            with session.begin():
                for data in bulk_data:
                    try:
                        resp = AgentRespone(**data)
                        session.add(resp)
                        session.flush()
                    except DBDuplicateEntry:
                        LOG.warning('Scheduler set agent overtime get a DBDuplicateEntry, Agent responed?')
                    except DBError as e:
                        count_finish += 1
                        LOG.error('Scheduler set agent overtime get DBError %s: %s' % (e.__class__.__name__, e.message))
        else:
            cache_store = get_cache()
            for data in bulk_data:
                respone_key = targetutils.async_request_key(request_id, agent_id)
                try:
                    if not cache_store.set(respone_key, jsonutils.dumps_as_bytes(data), ex=expire, nx=True):
                        LOG.warning('Scheduler set agent overtime to redis get a Duplicate Entry, Agent responed?')
                except RedisError as e:
                    LOG.error('Scheduler set agent overtime to redis get RedisError %s: %s' % (e.__class__.__name__,
                                                                                               e.message))
                    count_finish += 1
                    continue
        data = {'status': manager_common.FINISH, 'resultcode': manager_common.RESULT_SUCCESS}
        if count_finish < len(bulk_data):
            data.update({'resultcode': manager_common.RESULT_NOT_ALL_SUCCESS,
                         'result': 'fail some response, should %d, but just %d success' % (len(bulk_data),
                                                                                           count_finish)})
        query.update(data)
        session.commit()
