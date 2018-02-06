# -*- coding:utf-8 -*-
import random
import eventlet

from simpleflow.patterns import linear_flow as lf
from simpleflow.patterns import unordered_flow as uf

from goperation.manager.rpc.agent.application.taskflow import application
from goperation.manager.rpc.agent.application.taskflow import database
from goperation.manager.rpc.agent.application.taskflow.base import EntityTask
from goperation.manager.rpc.agent.application.taskflow.base import format_store_rebind


def entity_factory(session, app, store, db_flow_factory):
    """
    @param session:                 class: sqlalchemy:session
    @param middleware:              class: EntityMiddleware
    @param store:                   class: dict
    @param db_flow_factory:         class: function
    """
    endpoint_name = app.middleware.endpoint.namespace
    entity = app.middleware.entity
    entity_flow = lf.Flow('entity_%s_%d' % (endpoint_name, entity))

    if app.createtask:
        entity_flow.add(app.createtask)

    if app.stoptask:
        # kill if stop fail
        prepare_flow = uf.Flow('recheck_stop_%s_%d' % (endpoint_name, entity),
                               retry=application.AppKill('kill_%s_%d' % (endpoint_name, entity)))
        # sure entity stoped
        prepare_flow.add(app.stoptask)
        entity_flow.add(prepare_flow)

    upflow = uf.Flow('up_%s_%d' % (endpoint_name, entity))
    if app.upgradetask:
        # upgrade app file
        upflow.add(app.upgradetask)
    # backup and update app database
    database_flow = db_flow_factory(app, store)
    if database_flow:
        upflow.add(database_flow)
    if len(upflow):
        entity_flow.add(upflow)
    else:
        del upflow
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
                 db_flow_factory=database.mysql_flow_factory):
    """
    @param session:                 class: sqlalchemy:session
    @param middlewares:             class:list EntityMiddleware
    @param upgradefile:             class:AppUpgradeFile    app upgrade file
    @param backupfile:              class:basestring of path/AppRemoteBackupFile  app backup file
    @param store:                   class:dict
    @param db_flow_factory:         class:function
    """
    if not applications:
        raise RuntimeError('No application found')
    store = store or {}
    if store.get('backupfile'):
        raise RuntimeError('Backupfile in store')
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
    # else:
    #     if app.upgradetask:
    #         raise RuntimeError('Application upgrade need upgradefile')
    # 备份程序文件
    if backupfile:
        rebind = ['download_timeout']
        format_store_rebind(store, rebind)
        prepare_uflow.add(application.AppBackUp(app.middleware, backupfile, rebind=rebind))
    # else:
    #     if not store.get('backupfile'):
    #         if app.upgradetask and app.upgradetask.rollback:
    #             raise RuntimeError('upgrade rollback able, but no backupfile found')
    #     store.setdefault('backupfile', None)
    # 下载数据库更新文件
    if app.databases:
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
        entitys_taskflow.add(entity_factory(session, app, store, db_flow_factory))
        eventlet.sleep(0)
    main_flow.add(entitys_taskflow)

    return main_flow
