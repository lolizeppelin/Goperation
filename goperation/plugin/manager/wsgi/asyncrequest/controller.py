import webob.exc

from sqlalchemy.sql import or_
from sqlalchemy.sql import and_

from redis.exceptions import RedisError

from simpleutil.utils import argutils
from simpleutil.utils import jsonutils
# from simpleutil.utils import timeutils
from simpleutil.log import log as logging

from simpleutil.common.exceptions import InvalidArgument

from simpleservice.ormdb.api import model_query

from goperation.plugin.manager import targetutils
from goperation.plugin.manager import common as manager_common
from goperation.plugin.manager.api import get_session
from goperation.plugin.manager.api import get_redis
from goperation.plugin.manager.models import AsyncRequest
from goperation.plugin.manager.models import AgentRespone
from goperation.plugin.manager.models import ResponeDetail
from goperation.plugin.manager.wsgi import resultutils
from goperation.plugin.manager.wsgi import contorller

from simpleservice.ormdb.exceptions import DBError
from simpleservice.ormdb.exceptions import DBDuplicateEntry

LOG = logging.getLogger(__name__)

FAULT_MAP = {InvalidArgument: webob.exc.HTTPClientError}

MAX_ROW_PER_REQUEST = 100


Idformater = argutils.Idformater(key='request_id')


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
        request = query.filter_by(request_id=request_id).first()
        if not request:
            raise InvalidArgument('Request id:%s can not be found' % request_id)
        if request.persist:
            return resultutils.async_request(request, agents, details)
        else:
            ret_dict = resultutils.async_request(request)
            _cache_server = get_redis()
            key_pattern = targetutils.async_request_pattern(request_id)
            respone_keys = _cache_server.keys(key_pattern)
            if not _cache_server.exists(respone_keys):
                return ret_dict
            agent_respones = _cache_server.mget(respone_keys)
            for agent_respone in agent_respones:
                ret_dict['respones'].append(jsonutils.loads(agent_respone))
            return ret_dict

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
                                   data=[resultutils.details(detail) for detail in details])

    @Idformater
    def update(self, req, request_id, body):
        """For scheduler update row of
        scheduler,deadline, and status and result"""
        scheduler = int(body.get('scheduler', 0))
        if scheduler <= 0:
            raise InvalidArgument('Async checker id is 0')
        data = {'scheduler': scheduler}
        session = get_session()
        with session.begin(subtransactions=True):
            query = model_query(session, AsyncRequest,
                                filter=or_(AsyncRequest.scheduler == 0,
                                           AsyncRequest.scheduler == scheduler))
            unfinish_request = query.filter_by(request_id=request_id,
                                               status=0).one_or_none()
            if not unfinish_request:
                raise InvalidArgument('Reuest is alreday finished or not exist')
            unfinish_request.scheduler = scheduler
            status = int(body.get('status', 0))
            if status not in (0, 1):
                raise InvalidArgument('Status value error, not 0 or 1')
            data['status'] = status
            # deadline = int(body.get('deadline', 0))
            # if deadline:
            #     if deadline < unfinish_request.deadline:
            #         raise InvalidArgument('New deadline time can not small then old deadline time')
            #     if deadline - unfinish_request.deadline > 3600:
            #         raise InvalidArgument('New deadline over old deleline time more then one hour')
            #     data['deadline'] = deadline
            result = body.get('result', None)
            if result:
                if len(result) > manager_common.MAX_REQUEST_RESULT:
                    raise InvalidArgument('Msg of request over range')
                unfinish_request.result = result
                data['result'] = result
            unfinish_request.update(data)
        return resultutils.results(result='Request %s update success' % request_id)

    @Idformater
    def respone(self, req, request_id, body):
        """agent report respone api"""
        try:
            agent_id = body.get('agent_id')
            agent_time = body.get('agent_time')
            resultcode = body.get('resultcode')
            result = body.get('result')
            details = body.get('details', [])
            persist = body.get('persist', 1)
            expire = body.get('expire', 30)
        except KeyError as e:
            raise InvalidArgument('Agent respone need key %s' % e.message)
        _cache_server = get_redis()
        session = get_session()
        data = dict(request_id=request_id,
                    agent_id=agent_id,
                    agent_time=agent_time,
                    resultcode=resultcode,
                    result=result,
                    details=[dict(agent_id=agent_id,
                                  request_id=request_id,
                                  detail_id=detail['detail'],
                                  resultcode=detail['resultcode'],
                                  result=detail['result'] if isinstance(detail['result'], basestring)
                                  else jsonutils.dump_as_bytes(detail['result']))
                             for detail in details])
        if persist and details:
            data['details'] = [ResponeDetail().update(detail) for detail in data.pop(details)]
            try:
                session.add(AgentRespone().update(data))
            except DBDuplicateEntry:
                LOG.warning('Agent %d respone %s get DBDuplicateEntry error' % (agent_id, request_id))
                query = model_query(session, AgentRespone,
                                    filter=and_(AgentRespone.request_id == request_id,
                                                AgentRespone.agent_id == agent_id))
                with session.begin(subtransactions=True):
                    respone = query.one()
                    if respone.resultcode != manager_common.RESULT_OVER_DEADLINE:
                        result = 'Agent %d respone %s fail,another agent with same agent_id in database' % \
                                 (agent_id, request_id)
                        LOG.error(result)
                        return resultutils.results(result=result,
                                                   resultcode=manager_common.RESULT_ERROR)
                    query.update(data)
        else:
            respone_key = targetutils.async_request_key(request_id, agent_id)
            try:
                if not _cache_server.set(respone_key, jsonutils.dump_as_bytes(data), ex=expire, nx=True):
                    LOG.warning('Scheduler set agent overtime to redis get a Duplicate Entry, Agent responed?')
                    respone = jsonutils.loads(_cache_server.get(respone_key))
                    if respone.get('resultcode') != manager_common.RESULT_OVER_DEADLINE:
                        result = 'Agent %d respone %s fail,another agent ' \
                                 'with same agent_id in redis' % (agent_id, request_id)
                        LOG.error(result)
                        return resultutils.results(result=result,resultcode=manager_common.RESULT_ERROR)
                    # overwirte respone_key
                    _cache_server.set(respone_key, jsonutils.dump_as_bytes(data), ex=expire, nx=False)
            except RedisError as e:
                LOG.error('Scheduler set agent overtime to redis get RedisError %s: %s' % (e.__class__.__name__,
                                                                                           e.message))
                result = 'Agent %d respne %s fail, write to redis fail' % \
                         (agent_id, request_id)
                return resultutils.results(result=result,
                                           resultcode=manager_common.RESULT_ERROR)
        return resultutils.results(result='Agent %d Post respone of %s success' % (agent_id, request_id))

    @Idformater
    def overtime(self, req, request_id, body):
        """agent not resopne, async checker send a overtime respone"""
        agents = body.get('agents')
        agent_time = body.get('agent_time')
        scheduler = body.get('scheduler')
        persist = body.get('persist', 1)
        expire = body.get('expire', 30)
        session = get_session()
        _cache_server = get_redis()
        for agent_id in agents:
            data = dict(request_id=request_id,
                        agent_id=agent_id,
                        agent_time=agent_time,
                        resultcode=manager_common.RESULT_OVER_DEADLINE,
                        result='Agent respone overtime, report by Scheduler:%d' % scheduler,)
                        # status=manager_common.STATUS_OVER_TIME)
            if persist:
                try:
                    session.add(AgentRespone().update(data))
                except DBDuplicateEntry:
                    LOG.warning('Scheduler set agent overtime get a DBDuplicateEntry, Agent responed?')
                except DBError as e:
                    LOG.error('Scheduler set agent overtime get DBError %s: %s' % (e.__class__.__name__, e.message))
            else:
                respone_key = targetutils.async_request_key(request_id, agent_id)
                try:
                     if not _cache_server.set(respone_key, jsonutils.dump_as_bytes(data), ex=expire, nx=True):
                        LOG.warning('Scheduler set agent overtime to redis get a Duplicate Entry, Agent responed?')
                except RedisError as e:
                    LOG.error('Scheduler set agent overtime to redis get RedisError %s: %s' % (e.__class__.__name__,
                                                                                               e.message))
        return resultutils.results(result='Scheduler post agent overtime success')