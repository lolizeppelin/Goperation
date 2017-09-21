import sys
import random
from goperation.manager.models import *
from sqlalchemy import MetaData
from simpleutil.utils import uuidutils
from simpleservice.ormdb.argformater import connformater
from simpleservice.ormdb import orm
from simpleservice.ormdb.api import model_query
from simpleservice.ormdb.api import model_count_with_key
from simpleservice.ormdb.api import model_max_with_key
from simpleservice.ormdb.api import model_autoincrement_id
from simpleservice.ormdb.engines import create_engine
from goperation.manager import common

dst = {'host': '172.20.0.3',
       'port': 3304,
       'schema': 'manager',
       'user': 'root',
       'passwd': '111111'}

agent_id = random.randint(1, 100)

sql_connection = connformater % dst

engine = create_engine(sql_connection)


metadata = MetaData()
metadata.reflect(bind=engine)

for tab in metadata.tables.keys():
    print tab

session_maker = orm.get_maker(engine=engine)
session = session_maker()

print 'init session finish'
print '~~~~~~~~~~~~~~~~~~~~~~~~~~'


print 'test add request_row'
request_row = AsyncRequest()
with session.begin():
    session.add(request_row)
print request_row
print request_row.request_id
print 'test add request_row finish'
print '~~~~~~~~~~~~~~~~~~~~~~~~~~'

print 'test add agent_row'
agent_row = Agent()
agent_row.host = uuidutils.generate_uuid()[:5]
agent_row.agent_type = common.APPLICATION
agent_row.agent_id = agent_id
with session.begin(subtransactions=True):
    session.add(agent_row)
print agent_row
print agent_row.agent_id
print 'test add agent_row finish'
print '~~~~~~~~~~~~~~~~~~~~~~~~~~'


print '~~~~~test filter_by~~~~~~~'
with session.begin():
    query = model_query(session, AsyncRequest)
    rets = query.filter_by(request_id=request_row.request_id).all()
    print rets
    ret = query.filter_by(request_id=request_row.request_id).first()
    print ret, ret.to_dict()
    print 'scalar:',
    print query.filter_by(request_id=request_row.request_id).scalar()
print '~~~~~test filter~~~~~~~'

with session.begin():
    query = model_query(session, AsyncRequest, filter={'request_id': request_row.request_id})
    rets = query.all()
    print rets
    ret = query.first()
    print ret, ret.to_dict()
    print 'scalar:',
    print query.scalar()
print '~~~~~~~~~~~~~~~~~~~~~~~~~~'

print '~~~~~test function~~~~~~~'

print 'count agent', model_count_with_key(session, Agent)
print 'count agent.agent_id', model_count_with_key(session, Agent.agent_id)
print 'max agent.agent_id', model_max_with_key(session, Agent.agent_id)
print 'max + 1 agent.agent_id', model_autoincrement_id(session, Agent.agent_id)
print '~~~~~test function finish~~~~~~~'
print '~~~~~test CASCADE~~~~~~~'

print '~~~~~~~~~~CASCADE of endpoint~~~~~~~~~~~~~~~~'
endpont = AgentEndpoint()
endpont.endpoint = 'test'
agent_row.endpoints = [endpont, ]
with session.begin():
    session.add(agent_row)

print agent_row
print agent_row.endpoints

with session.begin():
    print 'CASCADE of update test'
    agent_row.update({'agent_id': agent_id + 1})

if model_count_with_key(session, AgentEndpoint, filter={'agent_id': agent_id, 'endpoint': 'test'}) > 0:
    print agent_id, agent_row.agent_id
    print 'CASCADE of endpoint fail, find old'
    sys.exit(0)

if not model_count_with_key(session, AgentEndpoint,
                            filter={'agent_id': agent_id + 1, 'endpoint': 'test'}) > 0:
    print 'CASCADE of endpoint fail, not find new'
    sys.exit(0)

print 'CASCADE of update success'

with session.begin():
    print 'CASCADE of delete test'
    session.delete(agent_row)

endpont = AgentEndpoint()
endpont.endpoint = 'test'
endpont.agent_id = agent_id

if model_count_with_key(session, AgentEndpoint,
                        filter={'agent_id': agent_id + 1, 'endpoint': 'test'}) > 0:
    print 'CASCADE of endpoint fail'
    sys.exit(0)

print 'endpoint delete success'

success = False

try:
    with session.begin():
        session.add(endpont)
except Exception:
    import eventlet
    eventlet.sleep(0.01)
    print 'Traceback writed by LOG.exception'
    print '~~~~~~~~~~no error, it ok~~~~~~~~~~~~~~'
    success = True

if not success:
    print 'CASCADE of endpoint fail'
    sys.exit(0)


print '~~~~~~~~~~CASCADE of AgentRespone~~~~~~~~~~~~~~~~'

agent_row = Agent()
agent_row.host = uuidutils.generate_uuid()[:5]
agent_row.agent_type = common.APPLICATION
agent_row.agent_id = agent_id
with session.begin(subtransactions=True):
    session.add(agent_row)

respone = AgentRespone()
respone.agent_id = agent_id
respone.request_id = request_row.request_id
respone.agent_time = int(timeutils.realnow())

detile0 = ResponeDetail()
detile0.detail_id = 0
detile1 = ResponeDetail()
detile0.detail_id = 1

respone.details = [detile0, detile1]
with session.begin():
    session.add(respone)
# sys.exit(0)


with session.begin():
    session.delete(request_row)

print '~~~~~test CASCADE finish~~~~~~~'
