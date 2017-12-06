from simpleservice.wsgi import router
from simpleservice.wsgi.middleware import controller_return_response

from goperation.manager.wsgi.port import controller
from goperation.manager import common as manager_common

COLLECTION_ACTIONS = ['create', 'index']
MEMBER_ACTIONS = ['delete']


class Routers(router.RoutersBase):

    resource_name = manager_common.PORT
    collection_name = resource_name + 's'

    def append_routers(self, mapper, routers=None):
        controller_intance = controller_return_response(controller.PortReuest(),
                                                        controller.FAULT_MAP)
        collection = mapper.collection(collection_name=self.collection_name,
                                       resource_name=self.resource_name,
                                       controller=controller_intance,
                                       path_prefix='/%s/{agent_id}/%s/{endpoint}/%s/{entity}' %
                                                   (manager_common.AGENT,
                                                    manager_common.ENDPOINT,
                                                    manager_common.ENTITY),
                                       member_prefix='/{ports}',
                                       collection_actions=COLLECTION_ACTIONS,
                                       member_actions=MEMBER_ACTIONS)
        return collection
