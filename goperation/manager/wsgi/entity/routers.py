from simpleservice.wsgi import router
from simpleservice.wsgi.middleware import controller_return_response

from goperation.manager.wsgi.entity import controller
from goperation.manager import common as manager_common

COLLECTION_ACTIONS = ['create', 'index']
MEMBER_ACTIONS = ['show', 'delete']


class Routers(router.RoutersBase):

    resource_name = manager_common.ENTITY
    collection_name = resource_name + 's'

    def append_routers(self, mapper, routers=None):
        controller_intance = controller_return_response(controller.EntityReuest(),
                                                        controller.FAULT_MAP)
        collection = mapper.collection(collection_name=self.collection_name,
                                       resource_name=self.resource_name,
                                       controller=controller_intance,
                                       path_prefix='/%s/{endpoint}' % (manager_common.ENDPOINT + 's'),
                                       member_prefix='/{entity}',
                                       collection_actions=COLLECTION_ACTIONS,
                                       member_actions=MEMBER_ACTIONS)
        return collection
