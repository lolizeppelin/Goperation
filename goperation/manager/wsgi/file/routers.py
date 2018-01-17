from simpleservice.wsgi import router
from simpleservice.wsgi.middleware import controller_return_response

from goperation.manager.wsgi.file import controller
from goperation.manager import common as manager_common

COLLECTION_ACTIONS = ['index', 'create']
MEMBER_ACTIONS = ['show', 'update', 'delete']


class Routers(router.RoutersBase):

    resource_name = manager_common.FILE
    collection_name = resource_name + 's'

    def append_routers(self, mapper, routers=None):
        controller_intance = controller_return_response(controller.FileReuest(),
                                                        controller.FAULT_MAP)
        # list agent file
        self._add_resource(mapper, controller_intance,
                           path='/%s/{agent_id}/%s' % (manager_common.AGENT + 's',
                                                       self.collection_name),
                           get_action='list')
        # send file to agent
        self._add_resource(mapper, controller_intance,
                           path='/%s/{agent_id}/%s/{file_id}' % (manager_common.AGENT + 's',
                                                                 self.collection_name),
                           put_action='send')
        # delete file from agent
        self._add_resource(mapper, controller_intance,
                           path='/%s/{agent_id}/%s/{file_id}' % (manager_common.AGENT + 's',
                                                                 self.collection_name),
                           delete_action='clean')
        collection = mapper.collection(collection_name=self.collection_name,
                                       resource_name=self.resource_name,
                                       controller=controller_intance,
                                       member_prefix='/{file_id}',
                                       collection_actions=COLLECTION_ACTIONS,
                                       member_actions=MEMBER_ACTIONS)
        return collection
