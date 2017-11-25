from redis import StrictRedis
from redis.exceptions import RedisError
from sqlalchemy.sql import and_
from sqlalchemy.sql import or_
from sqlalchemy.orm.session import Session

from simpleservice.ormdb.exceptions import DBDuplicateEntry
from simpleservice.ormdb.exceptions import DBError

from simpleutil.utils import jsonutils
from simpleservice.ormdb.api import model_query

from goperation.manager import common as manager_common
from goperation.manager.utils import targetutils
from goperation.manager.utils import resultutils
from goperation.manager.models import AgentRespone
from goperation.manager.models import ResponeDetail


RESPONESCHEMA = {
    'type': 'object',
    'required': ['agent_id', 'agent_time', 'resultcode'],
    'properties':
        {
            'agent_id': {'type': 'integer', 'minimum': 0},                                   # agent id
            'agent_time': {'type': 'integer', 'minimum': 0},                                 # agent respone time
            'resultcode': {'type': 'integer', 'minimum': -127, 'maxmum': 127},               # resultcode
            'result': {'type': 'string'},                                                    # result message
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


def norespones(storage, request_id, agents):
    response_agents = set()
    if isinstance(storage, Session):
        query = model_query(storage, AgentRespone.agent_id, filter=AgentRespone.request_id == request_id)
        # get response from database
        for r in query.all():
            response_agents.add(r[0])
        return agents - response_agents
    elif isinstance(storage, StrictRedis):
        key_pattern = targetutils.async_request_pattern(request_id)
        respone_keys = storage.keys(key_pattern)
        for key in respone_keys:
            response_agents.add(int(key.split('-')[-1]))
        return agents - response_agents
    else:
        raise NotImplementedError('norespones storage type error')


def agentrespone(storage, request_id, data):
    """agent report respone api"""
    jsonutils.schema_validate(RESPONESCHEMA, data)
    agent_id = data.get('agent_id')
    agent_time = data.get('agent_time')
    resultcode = data.get('resultcode')
    result = data.get('result', 'no result message')
    expire = data.get('expire', 60)
    details = [dict(agent_id=agent_id,
                    request_id=request_id,
                    detail_id=detail['detail'],
                    resultcode=detail['resultcode'],
                    result=detail['result'] if isinstance(detail['result'], basestring)
                    else jsonutils.dumps_as_bytes(detail['result'])) for detail in data.get('details', [])]
    data = dict(request_id=request_id,
                agent_id=agent_id,
                agent_time=agent_time,
                resultcode=resultcode,
                result=result,
                )
    if isinstance(storage, Session):
        try:
            with storage.begin():
                storage.add(AgentRespone(**data))
                storage.flush()
                for detail in details:
                    storage.add(ResponeDetail(**detail))
                    storage.flush()
        except DBDuplicateEntry:
            query = model_query(storage, AgentRespone,
                                filter=and_(AgentRespone.request_id == request_id,
                                            AgentRespone.agent_id == agent_id))
            with storage.begin(subtransactions=True):
                respone = query.one()
                if respone.resultcode != manager_common.RESULT_OVER_FINISHTIME:
                    result = 'Agent %d respone %s fail,another agent with same agent_id in database' % \
                             (agent_id, request_id)
                    return resultutils.results(result=result,
                                               resultcode=manager_common.RESULT_ERROR)
                query.update(data)
    elif isinstance(storage, StrictRedis):
        data.setdefault('details', details)
        respone_key = targetutils.async_request_key(request_id, agent_id)
        try:
            if not storage.set(respone_key, jsonutils.dumps_as_bytes(data), ex=expire, nx=True):
                respone = jsonutils.loads_as_bytes(storage.get(respone_key))
                if respone.get('resultcode') != manager_common.RESULT_OVER_FINISHTIME:
                    result = 'Agent %d respone %s fail,another agent ' \
                             'with same agent_id in redis' % (agent_id, request_id)
                    return resultutils.results(result=result, resultcode=manager_common.RESULT_ERROR)
                # overwirte respone_key
                storage.set(respone_key, jsonutils.dumps_as_bytes(data), ex=expire, nx=False)
        except RedisError:
            result = 'Agent %d respne %s fail, write to redis fail' % \
                     (agent_id, request_id)
            return resultutils.results(result=result,
                                       resultcode=manager_common.RESULT_ERROR)
    else:
        raise NotImplementedError('respone storage type error')
    return resultutils.results(result='Agent %d Post respone of %s success' % (agent_id, request_id))


def bluk_insert(storage, bulk_data, expire=60):
    insert = 0
    if bulk_data:
        request_id = bulk_data[0]['request_id']
        agent_id = bulk_data[0]['agent_id']
        if isinstance(storage, Session):
            with storage.begin():
                for data in bulk_data:
                    try:
                        resp = AgentRespone(**data)
                        storage.add(resp)
                        storage.flush()
                    except DBDuplicateEntry:
                        insert += 1
                        continue
        elif isinstance(storage, StrictRedis):
            for data in bulk_data:
                respone_key = targetutils.async_request_key(request_id, agent_id)
                if not storage.set(respone_key, jsonutils.dumps_as_bytes(data), ex=expire, nx=True):
                    insert += 1
        else:
            raise NotImplementedError('bluk insert storage type error')
    return insert
