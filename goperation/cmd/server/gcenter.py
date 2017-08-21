from simpleutil.config import cfg
from simpleutil.log import log as logging
from simpleutil.utils import importutils

from simpleservice.server import LaunchWrapper
from simpleservice.server import launch

from simpleservice.wsgi.config import wsgi_options
from simpleservice.wsgi.config import find_paste_abs
from simpleservice.wsgi.service import load_paste_app
from simpleservice.wsgi.service import LauncheWsgiServiceBase

from goperation import plugin
from goperation.plugin import config as plugin_config
from goperation.plugin.manager.wsgi.config import route_opts

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


def configure(config_files=None):
    # create a new project and group named gcenter
    gcenter_group = cfg.OptGroup(name='gcenter', title='group of goperation center')
    # init plugin config
    plugin_config.configure(gcenter_group, config_files)
    # set wsgi config
    CONF.register_opts(wsgi_options, group=gcenter_group)
    # set default of paste config
    CONF.set_default('paste_config', default='gcenter-paste.ini',
                     group=gcenter_group)
    # add gcenter extend route
    CONF.register_opts(route_opts, gcenter_group)
    for route in CONF[gcenter_group.name].routes:
        route_class = '%s.Route' % route
        plugin.EXTEND_ROUTES.append(importutils.import_class(route_class))
        LOG.info('Add core route %s success' % route)

    # set endpoint config
    if CONF.endpoints:
        for endpoint in CONF.endpoints:
            endpoint_group = CONF.register_group(endpoint.lower())
            CONF.register_opts(route_opts, endpoint_group)
            # add endpoint route
            for route in CONF[endpoint_group.name].routes:
                route_class = '%s.Route' % route
                plugin.EXTEND_ROUTES.append(importutils.import_class(route_class))
                LOG.info('Add endpoint route %s success' % route)

    paste_file_path = find_paste_abs(CONF[gcenter_group.name])
    return gcenter_group.name, paste_file_path


def run(config_files):
    name, paste_config = configure(config_files=config_files)
    LOG.info('Paste config file is %s' % paste_config)
    app = load_paste_app(name, paste_config)
    wrappers = []
    wsgi_service = LauncheWsgiServiceBase(name, app, plugin_threadpool=plugin.threadpool)
    wsgi_wrapper = LaunchWrapper(wsgi_service, CONF[name].wsgi_process)
    wrappers.append(wsgi_wrapper)
    launch(wrappers, CONF[name].user, CONF[name].group)
