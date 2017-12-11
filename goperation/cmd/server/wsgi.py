from simpleutil.config import cfg
from simpleutil.log import log as logging
from simpleutil.utils import importutils

from simpleservice.server import LaunchWrapper
from simpleservice.server import launch
from simpleservice.wsgi.config import find_paste_abs
from simpleservice.wsgi.config import wsgi_server_options
from simpleservice.wsgi.service import LauncheWsgiServiceBase
from simpleservice.wsgi.service import load_paste_app


from goperation import threadpool
from goperation import EXTEND_ROUTES
from goperation import config as goperation_config
from goperation.manager import common as manager_common
from goperation.manager.wsgi.config import route_opts


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


def configure(config_files=None, config_dirs=None):
    name = manager_common.SERVER
    # init goperation config
    gcenter_group = goperation_config.configure(name, config_files, config_dirs)
    # set wsgi config
    CONF.register_opts(wsgi_server_options, group=gcenter_group)
    # set default of paste config
    goperation_config.set_wsgi_default()
    # add gcenter extend route
    CONF.register_opts(route_opts, gcenter_group)
    for route in CONF[gcenter_group.name].routes:
        route_class = '%s.Route' % route
        EXTEND_ROUTES.append(importutils.import_class(route_class))
        LOG.info('Add core route %s success' % route)

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

    paste_file_path = find_paste_abs(CONF[gcenter_group.name])
    return gcenter_group.name, paste_file_path


def run(procname, config_files, config_dirs=None):
    name, paste_config = configure(config_files=config_files, config_dirs=config_dirs)
    LOG.debug('Paste config file is %s' % paste_config)
    app = load_paste_app(name, paste_config)
    wrappers = []
    wsgi_service = LauncheWsgiServiceBase(name, app, plugin_threadpool=threadpool)
    wsgi_wrapper = LaunchWrapper(service=wsgi_service,
                                 workers=wsgi_service.conf.wsgi_process)
    wrappers.append(wsgi_wrapper)
    launch(wrappers, procname=procname)

