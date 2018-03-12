from simpleservice.wsgi import router
from simpleservice.wsgi.middleware import controller_return_response

from goperation.manager.wsgi.entity import controller
from goperation.manager import common as manager_common

COLLECTION_ACTIONS = ['create', 'index']
MEMBER_ACTIONS = []


class Routers(router.RoutersBase):

    resource_name = manager_common.ENTITY
    collection_name = resource_name + 's'

    def append_routers(self, mapper, routers=None):
        controller_intance = controller_return_response(controller.EntityReuest(),
                                                        controller.FAULT_MAP)
        self._add_resource(mapper, controller_intance,
                   path='/%s/{endpoint}/entitys/{entity}' % (manager_common.ENDPOINT),
                   get_action='show')
        self._add_resource(mapper, controller_intance,
                   path='/%s/{endpoint}/entitys/{entity}' % (manager_common.ENDPOINT),
                   delete_action='delete')
        self._add_resource(mapper, controller_intance,
                           path='/%s/{endpoint}/entitys/{entity}/logs' % (manager_common.ENDPOINT),
                           get_action='logs')
        collection = mapper.collection(collection_name=self.collection_name,
                                       resource_name=self.resource_name,
                                       controller=controller_intance,
                                       path_prefix='/%s/{agent_id}/%s/{endpoint}' % (manager_common.AGENT,
                                                                                     manager_common.ENDPOINT),
                                       member_prefix='/{entity}',
                                       collection_actions=COLLECTION_ACTIONS,
                                       member_actions=MEMBER_ACTIONS)
        return collection
