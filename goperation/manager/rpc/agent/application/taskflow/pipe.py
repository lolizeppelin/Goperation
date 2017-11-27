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
    entity = app.middleware.entity
    entity_flow = lf.Flow('entity_%d' % entity)

    if app.createtask:
        entity_flow.add(app.createtask)

    if app.stoptask:
        # kill if stop fail
        prepare_flow = uf.Flow('recheck_stop_%d' % entity,
                               retry=application.AppKill('kill_%d' % entity))
        # sure entity stoped
        prepare_flow.add(app.stoptask)
        entity_flow.add(prepare_flow)

    upflow = uf.Flow('up_%d' % entity)
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
    @param upgradefile:             class:list AppUpgradeFile
    @param backupfile:              class:list basestring or AppRemoteBackupFile
    @param store:                   class:dict
    @param db_flow_factory:         class:function
    """
    if not applications:
        raise RuntimeError('No application found')
    store = store or {}
    main_flow = lf.Flow('%s_taskflow' % applications[0].middleware.endpoint)

    # choice one entity by randomizing the selection of middlewares
    app = applications[random.randint(0, len(applications)-1)]

    # prepare file for app update and database
    prepare_uflow = uf.Flow('prepare')
    if upgradefile:
        rebind = ['download_timeout']
        format_store_rebind(store, rebind)
        #  get app update file, all middlewares use same app upload file
        prepare_uflow.add(application.AppUpgradeFileGet(app.middleware, upgradefile, rebind=rebind))
    else:
        if app.upgradetask:
            raise RuntimeError('Application upgrade need upgradefile')
    if backupfile:
        store.pop('backupfile', None)
        rebind = ['download_timeout']
        format_store_rebind(store, rebind)
        prepare_uflow.add(application.AppBackUp(app.middleware, backupfile, rebind=rebind))
    else:
        if not store.get('backupfile'):
            if app.upgradetask and app.upgradetask.rollback:
                raise RuntimeError('upgrade rollback able, but no backupfile found')
        store.setdefault('backupfile', None)
    if app.databases:
        rebind = ['download_timeout']
        format_store_rebind(store, rebind)
        # get database upload file, all middlewares use same database upload file
        prepare_uflow.add(database.DbUpdateSqlGet(app.middleware, app.databases, rebind=rebind))
    if len(prepare_uflow):
        main_flow.add(prepare_uflow)
    else:
        del prepare_uflow

    entitys_taskflow = uf.Flow('entitys_task')
    for app in applications:
        # all entity task
        entitys_taskflow.add(entity_factory(session, app, store, db_flow_factory))
        eventlet.sleep(0)
    main_flow.add(entitys_taskflow)

    return main_flow
