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


@singleton.singleton
class AsyncWorkRequest(contorller.BaseContorller):

    def index(self, req, body):
        session = get_session(readonly=True)
        order = body.get('order', None)
        desc = body.get('desc', False)
        status = body.get('status', 1)
        page_num = body.pop('page_num', 0)
        if status not in (0, 1):
            raise InvalidArgument('Status value error, not 0 or 1')
        # index in request_time
        # so first filter is request_time
        filter_list = []
        start_time = int(body.get('start_time', 0))
        end_time = int(body.get('start_time', 0))
        if start_time:
            filter_list.append(AsyncRequest.request_time >= start_time)
        if end_time:
            if end_time < start_time:
                raise InvalidArgument('end time less then start time')
            filter_list.append(AsyncRequest.request_time < end_time)
        filter_list.append(AsyncRequest.status == status)
        sync = body.get('sync', True)
        async = body.get('async', True)
        if not sync and async:
            raise InvalidArgument('No both sync and async mark')
        if sync and not async:
            filter_list.append(AsyncRequest.scheduler == 0)
        elif async and not sync:
            filter_list.append(AsyncRequest.scheduler != 0)
        request_filter = and_(*filter_list)
        return resultutils.bulk_results(session,
                                        model=AsyncRequest,
                                        columns=[AsyncRequest.request_id,
                                                 AsyncRequest.status,
                                                 AsyncRequest.request_time,
                                                 AsyncRequest.scheduler,
                                                 AsyncRequest.result
                                                 ],
                                        counter=AsyncRequest.request_id,
                                        order=order, desc=desc,
                                        filter=request_filter, page_num=page_num)

    @Idformater
    def show(self, req, request_id, body):
        request_id = request_id.pop()
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
        try:
            agent_id = body.pop('agent_id')
            agent_time = body.pop('agent_time')
            resultcode = body.pop('resultcode')
            result = body.pop('result')
        except KeyError as e:
            raise InvalidArgument('Agent respone need key %s' % e.message)
        details=[dict(agent_id=agent_id,
                      request_id=request_id,
                      detail_id=detail['detail'],
                      resultcode=detail['resultcode'],
                      result=detail['result'] if isinstance(detail['result'], basestring)
                      else jsonutils.dumps_as_bytes(detail['result'])) for detail in body.pop('details', [])]
        persist = body.pop('persist', 1)
        expire = body.pop('expire', 30)
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
        """"""
        persist = body.pop('persist', True)
        agents = argutils.map_to_int(body.pop('agents'))
        session = get_session(readonly=True)
        response_agents = set()
        if persist:
            query = model_query(session, AgentRespone.agent_id, filter=AgentRespone.request_id==request_id)
            # get response from database
            for r in query.all():
                response_agents.add(r[0])
        else:
            model_query(session, AsyncRequest, filter=AgentRespone.request_id==request_id).one()
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
            agent_id = body.get('agent_id')
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
        scheduler = body.get('scheduler')
        agent_time = body.get('agent_time')
        agents = body.get('agents')
        persist = body.get('persist', 1)
        expire = body.get('expire', 60)
        if not agents:
            raise InvalidArgument('Not agets report overtime?')
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
