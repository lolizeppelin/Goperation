from simpleservice.wsgi import router
from simpleservice.wsgi.middleware import controller_return_response

from goperation.manager.wsgi.agent import controller
from goperation.manager import common as manager_common

COLLECTION_ACTIONS = ['index', 'create']
MEMBER_ACTIONS = ['show', 'update', 'delete']


class Routers(router.RoutersBase):

    resource_name = manager_common.AGENT
    collection_name = resource_name + 's'

    def append_routers(self, mapper, routers=None):
        controller_intance = controller_return_response(controller.AgentReuest(),
                                                        controller.FAULT_MAP)
        # agent report online
        self._add_resource(mapper, controller_intance,
                           path='/%s/online' % self.collection_name,
                           put_action='online')
        self._add_resource(mapper, controller_intance,
                           path='/%s/flush' % self.collection_name,
                           post_action='flush')
        collection = mapper.collection(collection_name=self.collection_name,
                                       resource_name=self.resource_name,
                                       controller=controller_intance,
                                       member_prefix='/{agent_id}',
                                       collection_actions=COLLECTION_ACTIONS,
                                       member_actions=MEMBER_ACTIONS)
        # upgrade agent code (upgrade rpm package)
        collection.member.link('upgrade', method='POST')
        # change agent status
        collection.member.link('active', method='PATCH')
        # send async request to check agent status
        collection.member.link('status', method='GET')
        # edit agent
        collection.member.link('edit', method='PATCH')
        # send file to agent
        collection.member.link('file', name='send_file', action='send_file', method='PUT')
        # get alloced ports
        collection.member.link('ports', name='get_ports', action='get_ports', method='GET')
        # alloced  ports
        collection.member.link('ports', name='add_ports', action='add_ports', method='POST')
        # release ports
        collection.member.link('ports', name='delete_ports', action='delete_ports', method='DELETE')
        # add endpoint
        collection.member.link('endpoints', name='add_endpoints', action='add_endpoints', method='POST')
        # delete endpoint
        collection.member.link('endpoints', name='delete_endpoints', action='delete_endpoints', method='DELETE')
        return collection
