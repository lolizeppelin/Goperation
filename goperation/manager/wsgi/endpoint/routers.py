from simpleservice.wsgi import router
from simpleservice.wsgi.middleware import controller_return_response

from goperation.manager.wsgi.endpoint import controller
from goperation.manager import common as manager_common

COLLECTION_ACTIONS = ['create', 'index']
MEMBER_ACTIONS = ['show', 'delete']


class Routers(router.RoutersBase):

    resource_name = manager_common.ENDPOINT
    collection_name = resource_name + 's'

    def append_routers(self, mapper, routers=None):
        controller_intance = controller_return_response(controller.EndpointReuest(),
                                                        controller.FAULT_MAP)
        self._add_resource(mapper, controller_intance,
                   path='/%s/{endpoint}/agents' % self.collection_name,
                   get_action='agents')
        self._add_resource(mapper, controller_intance,
                   path='/%s/{endpoint}/entitys' % self.collection_name,
                   get_action='entitys')
        self._add_resource(mapper, controller_intance,
                   path='/%s/{endpoint}/count' % self.collection_name,
                   get_action='count')
        collection = mapper.collection(collection_name=self.collection_name,
                                       resource_name=self.resource_name,
                                       controller=controller_intance,
                                       path_prefix='/%s/{agent_id}' % (manager_common.AGENT + 's'),
                                       member_prefix='/{endpoint}',
                                       collection_actions=COLLECTION_ACTIONS,
                                       member_actions=MEMBER_ACTIONS,
                                       )
        return collection
