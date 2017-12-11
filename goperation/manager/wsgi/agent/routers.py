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
        self._add_resource(mapper, controller_intance,
                       path='/allagents',
                       get_action='allagents')

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
        # delete recode of deleted agent
        collection.member.link('clean', method='POST')
        # agent report system info
        collection.member.link('report', method='POST')
        return collection
