from simpleutil.config import cfg
from simpleutil.log import log as logging


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


def configure(config_files=None, config_dirs=None):
    from goperation.manager import common as manager_common
    from goperation import config as goperation_config

    # create a new project and group named gcenter
    name = manager_common.SERVER
    # init goperation config
    gcenter_group = goperation_config.configure(name, config_files, config_dirs)
    # init endpoint opts
    CONF.register_opts(goperation_config.endpoint_load_opts)

    from simpleutil.utils import importutils
    from simpleservice.wsgi.config import wsgi_server_options
    from simpleservice.wsgi.config import find_paste_abs

    from goperation import EXTEND_ROUTES
    from goperation import OPEN_ROUTES
    from goperation import CORE_ROUTES

    from goperation.manager.wsgi.config import route_opts

    from goperation.manager.wsgi.agent import routers as agent_routes
    from goperation.manager.wsgi.file import routers as file_routes
    from goperation.manager.wsgi.port import routers as port_routes
    from goperation.manager.wsgi.endpoint import routers as endpoint_routes
    from goperation.manager.wsgi.entity import routers as entity_routes
    from goperation.manager.wsgi.cache import routers as cache_routes
    from goperation.manager.wsgi.asyncrequest import routers as asyncrequest_routes
    from goperation.manager.wsgi.agent.scheduler import routers as scheduler_routes
    from goperation.manager.wsgi.agent.application import routers as application_routes

    # insert core routes
    CORE_ROUTES.extend([port_routes, entity_routes, endpoint_routes, agent_routes,
                        scheduler_routes, application_routes, asyncrequest_routes,
                        cache_routes, file_routes])

    # set wsgi config
    CONF.register_opts(wsgi_server_options, group=gcenter_group)
    # set default of paste config
    goperation_config.set_wsgi_default()
    # add gcenter extend route
    CONF.register_opts(route_opts, gcenter_group)

    for cls in CONF[gcenter_group.name].routes:
        # route_class = '%s.Routers' % route
        EXTEND_ROUTES.append(importutils.import_module(cls))
        LOG.debug('Add extend route %s success' % cls)

    for cls in CONF[gcenter_group.name].publics:
        # route_class = '%s.Routers' % route
        OPEN_ROUTES.append(importutils.import_module(cls))
        LOG.debug('Add public route %s success' % cls)

    # set endpoint config
    if CONF.endpoints:
        for endpoint in CONF.endpoints:
            endpoint_group = cfg.OptGroup(endpoint.lower(),
                                          title='endpopint of %s' % endpoint)
            CONF.register_group(endpoint_group)
            CONF.register_opts(route_opts, endpoint_group)
            # add endpoint route
            for cls in CONF[endpoint_group.name].routes:
                EXTEND_ROUTES.append(importutils.import_module(cls))
                LOG.debug('Add endpoint route %s success' % cls)
            for cls in CONF[endpoint_group.name].publics:
                OPEN_ROUTES.append(importutils.import_module(cls))
                LOG.debug('Add endpoint public route %s success' % cls)

    paste_file_path = find_paste_abs(CONF[gcenter_group.name])
    return gcenter_group.name, paste_file_path


def run(procname, config_files, config_dirs=None):
    name, paste_config = configure(config_files=config_files, config_dirs=config_dirs)
    LOG.debug('Paste config file is %s' % paste_config)

    from simpleservice.wsgi.service import load_paste_app
    from simpleservice.wsgi.service import LauncheWsgiServiceBase
    from simpleservice.server import LaunchWrapper
    from simpleservice.server import launch
    from goperation import threadpool

    app = load_paste_app(name, paste_config)
    wrappers = []
    wsgi_service = LauncheWsgiServiceBase(name, app, plugin_threadpool=threadpool)
    wsgi_wrapper = LaunchWrapper(service=wsgi_service,
                                 workers=wsgi_service.conf.wsgi_process)
    wrappers.append(wsgi_wrapper)
    launch(wrappers, procname=procname)
