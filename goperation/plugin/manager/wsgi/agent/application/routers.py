from simpleservice.wsgi import router
from goperation.plugin.manager import common as manager_common

MEMBER_ACTIONS = ['show']
COLLECTION_ACTIONS = ['index']


class Routers(router.RoutersBase):

    resource_name = manager_common.APPLICATION
    collection_name = resource_name + 's'

    pass