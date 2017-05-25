from simpleservice.plugin.utils import init_plugin_database

from goperation.plugin.manager import models as manager_models

def init_manager(db_info):
    init_plugin_database(db_info, manager_models)