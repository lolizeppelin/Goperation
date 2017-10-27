from simpleservice.wsgi import router
from simpleservice.wsgi.middleware import controller_return_response

from goperation.manager.wsgi.endpoint import controller
from goperation.manager import common as manager_common

COLLECTION_ACTIONS = ['create']
MEMBER_ACTIONS = ['show', 'delete']


class Routers(router.RoutersBase):

    resource_name = manager_common.ENDPOINT
    collection_name = resource_name + 's'

    def append_routers(self, mapper, routers=None):
        controller_intance = controller_return_response(controller.EndpointReuest(),
                                                        controller.FAULT_MAP)
        collection = mapper.collection(collection_name=self.collection_name,
                                       resource_name=self.resource_name,
                                       controller=controller_intance,
                                       # path_prefix='/%s/{agent_id}' % (manager_common.AGENT + 's'),
                                       path_prefix='/%s/{agent_id}/%s/{endpoint}/%s/{entity}' %
                                                   (manager_common.AGENT + 's',
                                                    manager_common.ENDPOINT + 's',
                                                    manager_common.ENTITY + 's'),
                                       member_prefix='/{ports}',
                                       collection_actions=COLLECTION_ACTIONS,
                                       member_actions=MEMBER_ACTIONS)
        return collection
