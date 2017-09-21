# -*- coding: utf-8 -*-
import os

import eventlet
from goperation.taskflow.taskpipe import app

from goperation.manager.rpc.agent.application.taskflow import application
from goperation.taskflow import middleware
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

entity = 1
endpoint = 'mszl'
entity_home = os.path.join(work_bask, 'entity_%d' % entity)

update_base = 'C:\\Users\\loliz_000\\Desktop\\update'
backup_base = 'C:\\Users\\loliz_000\\Desktop\\backup'

backup_file = os.path.join(backup_base, 'wtf.tar.gz')


class FileManager():
    """测试用 file manager"""

    def get(self, target, download=True, timeout=None):
        for name in os.listdir(update_base):
            if name.startswith(target.source):
                return os.path.join(update_base, name)
        raise RuntimeError('No file found')

    def __repr__(self):
        return 'FileManager'


upgrade = application.AppUpgradeFile(source='nova')

_appcation = application.Appcation(upgrade=upgrade, backup=backup_file)

m = middleware.EntityMiddleware(entity=1, endpoint=endpoint, entity_home=entity_home,
                                appcation=_appcation)


store = {'filemanager': FileManager()}

main_flow = app.flow_factory(session=session, middlewares=[m, ], store=store)

print store