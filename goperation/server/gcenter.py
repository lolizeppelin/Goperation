

from simpleutil.config import cfg
from simpleutil.log import log as logging
from simpleutil.utils import importutils

from simpleservice.server import ServerWrapper
from simpleservice.server import launch

from simpleservice.wsgi.config import wsgi_options
from simpleservice.wsgi.service import load_paste_app
from simpleservice.wsgi.service import LauncheWsgiServiceBase

from goperation import plugin
from goperation.plugin import defaultcfg

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


def configure(config_files=None):
    # create a new project and group named gcenter
    gcenter_group = cfg.OptGroup(name='gcenter', title='group of goperation center')
    CONF(project=gcenter_group.name,
         default_config_files=config_files)
    CONF.register_group(gcenter_group)

    # set some public config
    defaultcfg.configure(gcenter_group.name, log_levels=['routes=INFO', ])

    # set wsgi config
    CONF.register_opts(wsgi_options, group=gcenter_group)
    CONF.set_default('paste_config', group=gcenter_group,
                     default='gcenter-paste.ini')

    # set manager config
    manager_entity = importutils.import_class(CONF.manager_entity)
    # import extend route of manager
    if CONF[manager_entity.name].routes:
        for route in CONF[manager_entity.name].routes:
            plugin.EXTEND_ROUTES.append(importutils.import_class(route))

    # set endpoint config
    if CONF.endpoints:
        for endpoint in CONF.endpoints:
            endpoint_group = importutils.import_class(endpoint)
            # add endpoint route
            for route in CONF[endpoint_group.name].routes:
                plugin.EXTEND_ROUTES.append(importutils.import_class(route))
    paste_fild_path = defaultcfg.find_paste_abs(CONF[gcenter_group.name])
    return gcenter_group.name, paste_fild_path


def run(config_files):
    name, paste_config = configure(config_files=config_files)
    app = load_paste_app(name, paste_config)
    servers = []
    wsgi_server = LauncheWsgiServiceBase(name, app)
    wsgi_wrapper = ServerWrapper(wsgi_server, CONF[name].wsgi_process)
    servers.append(wsgi_wrapper)
    launch(servers, CONF.user, CONF.group)
