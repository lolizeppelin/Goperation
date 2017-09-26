# -*- coding: utf-8 -*-
import os
import eventlet

from test.unit.taskflow import test_group
from test.unit.taskflow import TestEndpoint
from test.unit.taskflow import TestManager
from goperation.manager.rpc.agent.application.taskflow import application
from goperation.manager.rpc.agent.application.taskflow import middleware
from goperation.manager.rpc.agent.application.taskflow import pipe
from simpleflow.utils.storage_utils import build_session
from simpleservice.ormdb.argformater import connformater

eventlet.monkey_patch()
dst = {'host': '172.20.0.3',
       'port': 3304,
       'schema': 'simpleflow',
       'user': 'root',
       'passwd': '111111'}
sql_connection = connformater % dst
session = build_session(sql_connection)


work_bask = 'C:\\Users\\loliz_000\\Desktop\\work'
update_base = 'C:\\Users\\loliz_000\\Desktop\\update'
backup_base = 'C:\\Users\\loliz_000\\Desktop\\backup'

backup_file = os.path.join(backup_base, 'wtf.tar.gz')


mananager = TestManager(work_bask, update_base)
endpoint = TestEndpoint(manager=mananager, group=test_group)
_middleware = middleware.EntityMiddleware(entity=1, endpoint=endpoint)


upgrade = application.AppUpgradeFile(source='nova')

_appcation = application.Application(upgrade=upgrade, backup=backup_file)

m = middleware.EntityMiddleware(entity=1, endpoint=endpoint, application=_appcation)

store = {}

main_flow = pipe.flow_factory(session=session, middlewares=[m, ], store=store)

print store