# -*- coding: utf-8 -*-
import os
from goperation.manager.rpc.agent.application.taskflow import application
from goperation.manager.rpc.agent.application.taskflow import middleware
from goperation.manager.rpc.agent.application.taskflow import database
from goperation.manager.rpc.agent.application.taskflow import pipe
from simpleflow.utils.storage_utils import build_session
from simpleservice.ormdb.argformater import connformater


from simpleflow import api
from simpleflow.storage import Connection
from simpleflow.engines.engine import ParallelActionEngine


from simpleutil.config import cfg
from goperation.manager.rpc.agent.application.base import AppEndpointBase


test_group = cfg.OptGroup('testopt')


class TestFileManager():
    """测试用 file manager"""

    def __init__(self, update_base):
        self.update_base = update_base

    def get(self, target, download=True, timeout=None):
        for name in os.listdir(self.update_base):
            if name.startswith(target.source):
                target.realpath = os.path.join(self.update_base, name)
                return os.path.join(self.update_base, name)
        raise RuntimeError('No file found')


class TestManager(object):
    """测试用 manager"""
    def __init__(self, work_path, update_base=None):
        self.work_path = work_path
        self.filemanager = TestFileManager(update_base)




class TestEndpoint(AppEndpointBase):


    def __init__(self, manager, group):
        self.manager = manager
        self.group = group
        self.target = None
        self.namespace = group.name
        self._home_path = os.path.join(manager.work_path, self.namespace)

    def appname(self, entity):
        return 'app'

    def entity_user(self, entity):
        return None

    def entity_group(self, entity):
        return None

    def entity_home(self, entity):
        return os.path.join(self._home_path, 'entity_%d' % entity)


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

mananager = TestManager(work_bask, update_base)
endpoint = TestEndpoint(manager=mananager, group=test_group)


def stop(entity):
    print 'stop', entity


def kill(entity):
    print 'kill', entity


def update(entity):
    print 'update', entity


_appcation = application.Application(stopfunc=stop, killfunc=kill,
                                     updatefunc=update)


db_info = {'user': 'root',
           'passwd': '111111',
           'host': '172.20.0.3',
           'port': 3305,
           'schema': 'xiaohua_login'}

backup_file = os.path.join(backup_base, 'db.sql')

update = database.DbUpdateFile(source='update')

_database = database.Database(backup=backup_file, update=update,
                              **db_info)

m = middleware.EntityMiddleware(entity=1, endpoint=endpoint,
                                databases=[_database, ],
                                application=_appcation)

store = {}

main_flow = pipe.flow_factory(session=session, middlewares=[m, ], store=store)

connection = Connection(session)

engine = api.load(connection, main_flow, store=store, engine_cls=ParallelActionEngine)
engine.run()


for k, v in m.iterresults():
    print k,v

print store