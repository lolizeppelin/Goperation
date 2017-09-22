from simpleservice.wsgi import router
from goperation.manager import common as manager_common

MEMBER_ACTIONS = ['show']
COLLECTION_ACTIONS = ['index']


class Routers(router.RoutersBase):

    resource_name = manager_common.SCHEDULER
    collection_name = resource_name + 's'

    pass