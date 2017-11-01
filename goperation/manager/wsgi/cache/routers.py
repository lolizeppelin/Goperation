from simpleservice.wsgi import router
from simpleservice.wsgi.middleware import controller_return_response

from goperation.manager.wsgi.cache import controller


class Routers(router.RoutersBase):

    resource_name = 'cache'
    collection_name = resource_name + 's'

    def append_routers(self, mapper, routers=None):
        controller_intance = controller_return_response(controller.CacheReuest(),
                                                        controller.FAULT_MAP)
        # agent report online
        self._add_resource(mapper, controller_intance,
                           path='/%s/host/{host}/online' % self.collection_name,
                           post_action='online')
        self._add_resource(mapper, controller_intance,
                           path='/%s/flush' % self.collection_name,
                           post_action='flush')
        # collection = mapper.collection(collection_name=self.collection_name,
        #                                resource_name=self.resource_name,
        #                                controller=controller_intance,
        #                                path_prefix='/%s/{endpoint}' % (manager_common.ENDPOINT + 's'),
        #                                member_prefix='/{entity}',
        #                                collection_actions=COLLECTION_ACTIONS,
        #                                member_actions=MEMBER_ACTIONS)
        # return collection
