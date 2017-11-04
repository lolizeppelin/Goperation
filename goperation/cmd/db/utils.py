from simpleservice.plugin.utils import init_plugin_database

from goperation.manager import models as manager_models
from goperation.filemanager import models as filemanager_models


def init_manager(db_info):
    init_plugin_database(db_info, manager_models, filemanager_models)