from simpleservice.wsgi import router
from simpleservice.wsgi.middleware import controller_return_response

from goperation.plugin.manager.wsgi.agent import controller
from goperation.plugin.manager import common as manager_common

COLLECTION_ACTIONS = ['index', 'create']
MEMBER_ACTIONS = ['show', 'update', 'delete']


class Routers(router.RoutersBase):

    resource_name = manager_common.AGENT
    collection_name = resource_name + 's'

    def append_routers(self, mapper, routers=None):
        controller_intance = controller_return_response(controller.AgentReuest(),
                                                        controller.FAULT_MAP)
        collection = mapper.collection(collection_name=self.collection_name,
                                       resource_name=self.resource_name,
                                       controller=controller_intance,
                                       member_prefix='/{agent_id}',
                                       collection_actions=COLLECTION_ACTIONS,
                                       member_actions=MEMBER_ACTIONS)
        # agent report online
        collection.link('online', method='PUT')
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
        return collection
