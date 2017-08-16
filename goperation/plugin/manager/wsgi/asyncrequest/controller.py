import webob.exc
from redis.exceptions import RedisError

from sqlalchemy.sql import and_
from sqlalchemy.sql import or_

from simpleutil.log import log as logging
from simpleutil.common.exceptions import InvalidArgument
from simpleutil.utils import argutils
from simpleutil.utils import jsonutils

from simpleservice.ormdb.api import model_query
from simpleservice.ormdb.exceptions import DBDuplicateEntry
from simpleservice.ormdb.exceptions import DBError

from goperation.plugin.manager import common as manager_common
from goperation.plugin.manager.api import get_cache
from goperation.plugin.manager.api import get_session
from goperation.plugin.manager.models import AgentRespone
from goperation.plugin.manager.models import AsyncRequest
from goperation.plugin.manager.models import ResponeDetail
from goperation.plugin.manager.wsgi import contorller
from goperation.plugin.manager.wsgi import targetutils
from goperation.plugin.manager.wsgi import resultutils


LOG = logging.getLogger(__name__)

FAULT_MAP = {InvalidArgument: webob.exc.HTTPClientError}

MAX_ROW_PER_REQUEST = 100


Idformater = argutils.Idformater(key='request_id', formatfunc='request_id_check')


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
        request = query.filter_by(request_id=request_id).one_or_none()
        if not request:
            raise InvalidArgument('Request id:%s can not be found' % request_id)
        if request.persist:
            # get resopne from database
            return resultutils.async_request(request, agents, details)
        else:
            ret_dict = resultutils.async_request(request,
                                                 agents=False, details=False)
            _cache_server = get_cache()
            # get respone from cache redis server
            key_pattern = targetutils.async_request_pattern(request_id)
            respone_keys = _cache_server.keys(key_pattern)
            agent_respones = _cache_server.mget(respone_keys)
            if agent_respones:
                for agent_respone in agent_respones:
                    if agent_respone:
                        try:
                            agent_respone_data = jsonutils.loads(agent_respone)
                            if isinstance(agent_respone_data, (int, long)):
                                raise ValueError
                        except (TypeError, ValueError):
                            continue
                        ret_dict['respones'].append(agent_respone_data)
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
      raise NotImplementedError

    @Idformater
    def respone(self, req, request_id, body):
        """agent report respone api"""
        try:
            agent_id = body.pop('agent_id')
            agent_time = body.pop('agent_time')
            resultcode = body.pop('resultcode')
            result = body.pop('result')
            details = body.pop('details', [])
            persist = body.pop('persist', 1)
            expire = body.pop('expire', 30)
        except KeyError as e:
            raise InvalidArgument('Agent respone need key %s' % e.message)
        _cache_server = get_cache()
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
            data['details'] = [ResponeDetail(**detail) for detail in data.pop(details)]
            try:
                respone = AgentRespone(**data)
                session.add(respone)
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
            respone_key = targetutils.async_request_key(request_id, agent_id)
            try:
                if not _cache_server.set(respone_key, jsonutils.dump_as_bytes(data), ex=expire, nx=True):
                    LOG.warning('Scheduler set agent overtime to redis get a Duplicate Entry, Agent responed?')
                    respone = jsonutils.loads(_cache_server.get(respone_key))
                    if respone.get('resultcode') != manager_common.RESULT_OVER_FINISHTIME:
                        result = 'Agent %d respone %s fail,another agent ' \
                                 'with same agent_id in redis' % (agent_id, request_id)
                        LOG.error(result)
                        return resultutils.results(result=result, resultcode=manager_common.RESULT_ERROR)
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
    def scheduler(self, req, request_id, body):
        """scheduler declare async request check and
           scheduler mark saync request finish
        """
        scheduler = int(body.get('scheduler', 0))
        status = int(body.get('status', manager_common.UNFINISH))
        result = body.get('result', 'Scheduler declare')
        resultcode = body.get('resultcode', None)
        if scheduler <= 0:
            raise InvalidArgument('Async checker id is 0')
        if status not in (manager_common.FINISH, manager_common.UNFINISH):
            raise InvalidArgument('Async request status value error')
        data = {'scheduler': scheduler}
        if status:
            data.setdefault('status', status)
        if resultcode is not None:
            data.setdefault('resultcode', resultcode)
        if result:
            if not isinstance(result, basestring):
                raise InvalidArgument('Msg of result not basestring')
            if len(result) > manager_common.MAX_REQUEST_RESULT:
                raise InvalidArgument('Msg of result over range')
            data.setdefault('result', result)
        session = get_session()
        with session.begin(subtransactions=True):
            query = model_query(session, AsyncRequest,
                                filter=or_(AsyncRequest.scheduler == 0,
                                           AsyncRequest.scheduler == scheduler))
            unfinish_request = query.filter_by(request_id=request_id,
                                               status=manager_common.UNFINISH).one_or_none()
            if not unfinish_request:
                raise InvalidArgument('Reuest is alreday finished or not exist')
            unfinish_request.update(data)
        return resultutils.results(result='Request %s update scheduler and status success' % request_id)

    @Idformater
    def overtime(self, req, request_id, body):
        """agent not resopne, async checker send a overtime respone"""
        scheduler = body.get('scheduler')
        agent_time = body.get('agent_time')
        agents = body.get('agents')
        persist = body.get('persist', 1)
        expire = body.get('expire', 30)
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
        # TODO bluk_insert should run background
        self.bluk_insert(bulk_data, persist, expire)
        return resultutils.results(result='Scheduler post agent overtime success')

    @staticmethod
    def bluk_insert(bulk_data, persist, expire):
        # TODO shoud async write
        session = get_session()
        if not persist:
            _cache_server = get_cache()
        request_id = bulk_data[0]['request_id']
        agent_id = bulk_data[0]['agent_id']
        count_finish = 0
        for data in bulk_data:
            if persist:
                try:
                    resp = AgentRespone(**data)
                    session.add(resp)
                    session.commit()
                except DBDuplicateEntry:
                    count_finish += 1
                    LOG.warning('Scheduler set agent overtime get a DBDuplicateEntry, Agent responed?')
                except DBError as e:
                    LOG.error('Scheduler set agent overtime get DBError %s: %s' % (e.__class__.__name__, e.message))
            else:
                respone_key = targetutils.async_request_key(request_id, agent_id)
                try:
                    if not _cache_server.set(respone_key, jsonutils.dump_as_bytes(data), ex=expire, nx=True):
                        count_finish += 1
                        LOG.warning('Scheduler set agent overtime to redis get a Duplicate Entry, Agent responed?')
                except RedisError as e:
                    LOG.error('Scheduler set agent overtime to redis get RedisError %s: %s' % (e.__class__.__name__,
                                                                                               e.message))
        data = {'status': manager_common.FINISH, 'resultcode': manager_common.RESULT_SUCCESS}
        query = model_query(session, AsyncRequest).filter_by(request_id=request_id)
        if count_finish < len(bulk_data):
            data.update({'resultcode': manager_common.RESULT_NOT_ALL_SUCCESS})
        query.update(data)
        session.commit()