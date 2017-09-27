import random
import eventlet


from simpleflow.patterns import linear_flow as lf
from simpleflow.patterns import unordered_flow as uf

from goperation.manager.rpc.agent.application.taskflow import application
from goperation.manager.rpc.agent.application.taskflow import database
from goperation.taskflow.base import format_store_rebind
from goperation.taskflow.base import EntityTask


def entity_factory(session, middleware, store, db_flow_factory):
    """
    @param session:                 class: sqlalchemy:session
    @param middleware:              class: EntityMiddleware
    @param store:                   class: dict
    @param db_flow_factory:         class: function
    """
    entity_flow = lf.Flow('entity_%d' % middleware.entity)

    if middleware.application and middleware.application.stopfunc:
        # kill if stop fail
        prepare_flow = uf.Flow('recheck_stop', retry=application.AppKill('kill_%d' % middleware.entity))
        # sure entity stoped
        prepare_flow.add(application.AppStop(middleware))
        entity_flow.add(prepare_flow)

    uflow = uf.Flow('update_%d' % middleware.entity)
    if middleware.application and middleware.application.upgrade:
        # upgrade app file
        rebind = ['upgrade_timeout']
        format_store_rebind(store, rebind)
        uflow.add(application.AppFileUpgrade(middleware, rebind=rebind))
    # backup and update app database
    database_flow = db_flow_factory(middleware, store)
    if database_flow:
        uflow.add(database_flow)
    if len(uflow):
        entity_flow.add(uflow)
    else:
        del uflow
    # update app (some thing like hot fix or flush config)
    if middleware.application and middleware.application.updatefunc:
        entity_flow.add(application.AppUpdate(middleware))
    # start appserver
    if middleware.application and middleware.application.startfunc:
        entity_flow.add(application.AppStart(middleware))

    return EntityTask(session, entity_flow, store)


def flow_factory(session, middlewares, store,
                 db_flow_factory=database.mysql_flow_factory):
    """
    @param session:                 class: sqlalchemy:session
    @param middlewares:             class:list EntityMiddleware list
    @param store:                   class:dict
    @param db_flow_factory:         class:function
    """
    if not middlewares:
        raise RuntimeError('No middleware found')
    main_flow = lf.Flow('%s_taskflow' % middlewares[0].endpoint)

    # choice one entity by randomizing the selection of middlewares
    middleware = middlewares[random.randint(0, len(middlewares)-1)]

    # prepare file for app update and database
    prepare_uflow = uf.Flow('prepare')
    if middleware.application:
        if middleware.application.backup or \
                (middleware.application.upgrade and middleware.application.upgrade.remote_backup):
            # backup app file, all middlewares use same app backup file
            rebind = ['download_timeout']
            format_store_rebind(store, rebind)
            prepare_uflow.add(application.AppBackUp(middleware, rebind=rebind))
        if middleware.application.upgrade:
            rebind = ['download_timeout']
            format_store_rebind(store, rebind)
            #  get app update file, all middlewares use same app upload file
            prepare_uflow.add(application.AppUpgradeFileGet(middleware, rebind=rebind))
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
