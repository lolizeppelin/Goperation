# -*- coding:utf-8 -*-
import random
import eventlet

from simpleflow.task import Task
from simpleflow.patterns import linear_flow as lf
from simpleflow.patterns import unordered_flow as uf


from goperation.manager.rpc.agent.application.taskflow import application
from goperation.manager.rpc.agent.application.taskflow import database
from goperation.manager.rpc.agent.application.taskflow.base import EntityTask
from goperation.manager.rpc.agent.application.taskflow.base import TaskPublicFile
from goperation.manager.rpc.agent.application.taskflow.base import format_store_rebind


class ProvidesTask(Task):
    def __init__(self, name, upgradefile=None, backupfile=None):
        self.upgradefile = upgradefile
        self.backupfile = backupfile
        super(ProvidesTask, self).__init__(name=name, provides=['upgradefile', 'backupfile'])

    def execute(self):
        return self.upgradefile.file if self.upgradefile else None, \
               self.backupfile.file if self.backupfile else None


def entity_factory(session, app, store,
                   upgradefile, backupfile,
                   db_flow_factory, **kwargs):
    """
    @param session:                 class: sqlalchemy:session
    @param middleware:              class: EntityMiddleware
    @param store:                   class: dict
    @param db_flow_factory:         class: function
    @param upgradefile:             class: TaskPublicFile
    @param backupfile:              class: TaskPublicFile
    @param kwargs:                  class: create_cls,backup_cls,update_cls
    """
    endpoint_name = app.middleware.endpoint
    entity = app.middleware.entity
    entity_flow = lf.Flow('entity_%s_%d' % (endpoint_name, entity))
    # 为创建更新和备份提供文件
    entity_flow.add(ProvidesTask(name='provides_%s_%d' % (endpoint_name, entity),
                                 upgradefile=upgradefile,
                                 backupfile=backupfile))
    # 创建任务,串行
    if app.createtask:
        if not upgradefile:
            raise ValueError('No file found for createtask')
        entity_flow.add(app.createtask)
    # 停止任务,串行
    if app.stoptask:
        # kill if stop fail
        prepare_flow = uf.Flow('recheck_stop_%s_%d' % (endpoint_name, entity),
                               retry=application.AppKill('kill_%s_%d' % (endpoint_name, entity)))
        # sure entity stoped
        prepare_flow.add(app.stoptask)
        entity_flow.add(prepare_flow)

    # 更新任务(与其他任务并行)
    upflow = uf.Flow('up_%s_%d' % (endpoint_name, entity))
    if app.upgradetask:
        if not upgradefile:
            raise ValueError('No file found for upgradetask')
        # upgrade app file
        upflow.add(app.upgradetask)
    # 数据库备份与升级任务
    database_flow = db_flow_factory(app, store, **kwargs)
    if database_flow:
        upflow.add(database_flow)

    # 合并工作流
    if len(upflow):
        entity_flow.add(upflow)
    else:
        del upflow

    # 其他串行任务
    # update app (some thing like hotfix or flush config)
    if app.updatetask:
        entity_flow.add(app.updatetask)
    # start appserver
    if app.startstak:
        entity_flow.add(app.startstak)
    # start appserver
    if app.deletetask:
        entity_flow.add(app.deletetask)

    # entity task is independent event
    return EntityTask(session, entity_flow, store)


def flow_factory(session, applications,
                 upgradefile=None,
                 backupfile=None,
                 store=None,
                 db_flow_factory=database.mysql_flow_factory,
                 **kwargs):
    """
    @param session:                 class: sqlalchemy:session
    @param middlewares:             class:list EntityMiddleware
    @param upgradefile:             class:AppUpgradeFile    app upgrade file
    @param backupfile:              class:basestring of path/AppRemoteBackupFile  app backup file
    @param store:                   class:dict
    @param db_flow_factory:         class:function   默认database.mysql_flow_factory
    @param create_cls:              class:class      数据库创建任务类 参考database.MysqlCreate
    @param backup_cls:              class:class      数据库备份任务类 参考database.MysqlDump
    @param update_cls:              class:class      数据库更新任务类  参考database.MysqlUpdate
    """
    if not applications:
        raise RuntimeError('No application found')
    if upgradefile and not isinstance(upgradefile, TaskPublicFile):
        raise TypeError('upgradefile not TaskPublicFile')
    if backupfile and not isinstance(backupfile, TaskPublicFile):
        raise TypeError('backupfile not TaskPublicFile')
    store = store or {}
    if store.get('backupfile') or store.get('upgradefile'):
        raise RuntimeError('Backupfile or Upgradefile in store')

    endpoint_name = applications[0].middleware.endpoint

    main_flow = lf.Flow('%s_taskflow' % endpoint_name)

    # choice one entity by randomizing
    # 随机选择一个app
    app = applications[random.randint(0, len(applications)-1)]

    # prepare file for app update and database
    # 准备工作
    prepare_uflow = uf.Flow('%s_prepare' % endpoint_name)
    # 下载程序更新文件
    if upgradefile:
        rebind = ['download_timeout']
        format_store_rebind(store, rebind)
        #  get app update file, all middlewares use same app upload file
        prepare_uflow.add(application.AppUpgradeFileGet(app.middleware, upgradefile, rebind=rebind))
    # 备份程序文件
    if backupfile:
        rebind = ['download_timeout']
        format_store_rebind(store, rebind)
        prepare_uflow.add(application.AppBackUp(app.middleware, backupfile, rebind=rebind))
    # 下载数据库更新文件
    if app.databases and not all([False if d.update else True for d in app.databases]):
        rebind = ['download_timeout']
        format_store_rebind(store, rebind)
        # get database upload file, all middlewares use same database upload file
        prepare_uflow.add(database.DbUpdateSqlGet(app.middleware, app.databases, rebind=rebind))
    if len(prepare_uflow):
        main_flow.add(prepare_uflow)
    else:
        del prepare_uflow

    entitys_taskflow = uf.Flow('%s_entitys_task' % endpoint_name)
    # 批量更新操作
    for app in applications:
        # all entity task
        entitys_taskflow.add(entity_factory(session, app, store,
                                            upgradefile, backupfile,
                                            db_flow_factory, **kwargs))
        eventlet.sleep(0)
    main_flow.add(entitys_taskflow)

    return main_flow
