from simpleservice.plugin.manager.models import *

from simpleutil.utils import uuidutils
from simpleservice.ormdb.argformater import connformater
from simpleservice.ormdb import orm
from simpleservice.ormdb.api import model_query


from simpleservice.ormdb.engines import create_engine


dst = {'host':'172.20.0.3',
       'port':3304,
       'schema':'manager',
       'user':'root',
       'passwd':'111111'}

sql_connection = connformater % dst

engine = create_engine(sql_connection)

session_maker = orm.get_maker(engine=engine)
session = session_maker()

request_row =  WsgiRequest()
with session.begin():
    session.add(request_row)

print request_row
print request_row.request_id

agent_row =  Agent()
agent_row.host = uuidutils.generate_uuid()[:5]
with session.begin(subtransactions=True):
    session.add(agent_row)

print agent_row
print agent_row.agent_id


print '~~~~~test filter_by~~~~~~~'

with session.begin():
    query = model_query(session, WsgiRequest)
    rets = query.filter_by(request_id=request_row.request_id).all()
    print rets
    ret = query.filter_by(request_id=request_row.request_id).first()
    print ret
    print ret.to_dict()

print '~~~~~test filter~~~~~~~'

with session.begin():
    query = model_query(session, WsgiRequest, filter={'request_id':request_row.request_id})
    rets = query.all()
    print rets
    ret = query.first()
    print ret
    print ret.to_dict()


print '~~~~~test CASCADE~~~~~~~'

report_row = AgentReportLog()
report_row.agent_id = agent_row.agent_id


report_row.report_time = 0
report_row.running = 1
report_row.sleeping  = 0
report_row.num_fds = 1
report_row.num_threads = 1

report_row.context = 1111
report_row.interrupts = 2222
report_row.sinterrupts = 111


report_row.irq = 222
report_row.sirq = 313
report_row.user = 1
report_row.system = 2
report_row.nice = 3
report_row.iowait = 4

report_row.used = 23424
report_row.cached = 1231231
report_row.buffers = 43242
report_row.free = 4243

report_row.syn = 12312
report_row.enable = 34242
report_row.closeing = 342

with session.begin():
    session.add(report_row)


with session.begin():
    session.delete(agent_row)

with session.begin():
    print 'find agent with id %d' % agent_row.agent_id
    print agent_row
    query = model_query(session, Agent, filter={'agent_id':agent_row.agent_id})
    ret = query.first()
    print ret
    query = model_query(session, AgentReportLog, filter={'agent_id':agent_row.agent_id})
    ret = query.first()
    print ret
    print dir(query)


from sqlalchemy import MetaData
metadata = MetaData()
metadata.reflect(bind=engine)

for tab in metadata.tables.keys():
    print tab

print 'try get data from metada'

with session.begin():
    for tab in metadata.tables.keys():
        print tab, type(tab), type(metadata.tables[tab])
        if tab is not None:
            query = model_query(session, metadata.tables[tab])
            rets = query.all()
            if rets:
                print tab
                print rets

