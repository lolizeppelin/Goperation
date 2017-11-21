import random
import eventlet

from simpleflow.patterns import linear_flow as lf
from simpleflow.patterns import unordered_flow as uf

from goperation.manager.rpc.agent.application.taskflow import application
from goperation.manager.rpc.agent.application.taskflow import database
from goperation.manager.rpc.agent.application.taskflow.base import EntityTask
from goperation.manager.rpc.agent.application.taskflow.base import format_store_rebind


def entity_factory(session, middleware, store, db_flow_factory):
    """
    @param session:                 class: sqlalchemy:session
    @param middleware:              class: EntityMiddleware
    @param store:                   class: dict
    @param db_flow_factory:         class: function
    """
    entity_flow = lf.Flow('entity_%d' % middleware.entity)

    if middleware.application and middleware.application.createtask:
        entity_flow.add(middleware.application.createtask)

    if middleware.application and middleware.application.stoptask:
        # kill if stop fail
        prepare_flow = uf.Flow('recheck_stop_%d' % middleware.entity,
                               retry=application.AppKill('kill_%d' % middleware.entity))
        # sure entity stoped
        prepare_flow.add(middleware.application.stoptask)
        entity_flow.add(prepare_flow)

    upflow = uf.Flow('up_%d' % middleware.entity)
    if middleware.application and middleware.application.upgradetask:
        # upgrade app file
        upflow.add(middleware.application.upgradetask)
    # backup and update app database
    database_flow = db_flow_factory(middleware, store)
    if database_flow:
        upflow.add(database_flow)
    if len(upflow):
        entity_flow.add(upflow)
    else:
        del upflow
    # update app (some thing like hotfix or flush config)
    if middleware.application and middleware.application.updatetask:
        entity_flow.add(middleware.application.updatetask)
    # start appserver
    if middleware.application and middleware.application.startstak:
        entity_flow.add(middleware.application.startstak)
    # start appserver
    if middleware.application and middleware.application.deletetask:
        entity_flow.add(middleware.application.deletetask)
    # entity task is independent event
    return EntityTask(session, entity_flow, store)


def flow_factory(session, middlewares,
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
    if not middlewares:
        raise RuntimeError('No middleware found')
    store = store or {}
    main_flow = lf.Flow('%s_taskflow' % middlewares[0].endpoint)

    # choice one entity by randomizing the selection of middlewares
    middleware = middlewares[random.randint(0, len(middlewares)-1)]

    # prepare file for app update and database
    prepare_uflow = uf.Flow('prepare')
    if upgradefile:
        rebind = ['download_timeout']
        format_store_rebind(store, rebind)
        #  get app update file, all middlewares use same app upload file
        prepare_uflow.add(application.AppUpgradeFileGet(middleware, upgradefile, rebind=rebind))
    else:
        if middleware.application.upgradefunc:
            raise RuntimeError('Application upgrade need upgradefile')
    if backupfile:
        store.pop('backupfile', None)
        rebind = ['download_timeout']
        format_store_rebind(store, rebind)
        prepare_uflow.add(application.AppBackUp(middleware, backupfile, rebind=rebind))
    else:
        if not store.get('backupfile'):
            if middleware.application.upgradefunc.rollback:
                raise RuntimeError('upgrade rollback able, but no backupfile found')
        store.setdefault('backupfile', None)
    if middleware.databases:
        rebind = ['download_timeout']
        format_store_rebind(store, rebind)
        # get database upload file, all middlewares use same database upload file
        prepare_uflow.add(database.DbUpdateSqlGet(middleware, rebind=rebind))
    if len(prepare_uflow):
        main_flow.add(prepare_uflow)
    else:
        del prepare_uflow

    entitys_taskflow = uf.Flow('entitys_task')
    for middleware in middlewares:
        # all entity task
        entitys_taskflow.add(entity_factory(session, middleware, store, db_flow_factory))
        eventlet.sleep(0)
    main_flow.add(entitys_taskflow)

    return main_flow
