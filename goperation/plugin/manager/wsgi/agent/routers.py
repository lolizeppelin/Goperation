from simpleservice.wsgi import router
from simpleservice.wsgi.middleware import controller_return_response

from goperation.plugin.manager.wsgi.agent import controller

COLLECTION_ACTIONS = ['index', 'create']
MEMBER_ACTIONS = ['show', 'update', 'delete']


class Routers(router.RoutersBase):

    resource_name = 'agent'
    collection_name = resource_name + 's'

    def append_routers(self, mapper, routers):
        controller_intance = controller_return_response(controller.AgentReuest(),
                                                        controller.FAULT_MAP)
        collection = mapper.collection(collection_name=self.collection_name,
                                       resource_name=self.resource_name,
                                       controller=controller_intance,
                                       member_prefix='/{agent_id}',
                                       collection_actions=COLLECTION_ACTIONS,
                                       member_actions=MEMBER_ACTIONS)
        # send file to agent
        collection.member.link('file', method='POST')
        # upgrade agent code
        collection.member.link('upgrade', method='POST')
        collection.member.link('active', method='PUT')
        # agent show online when it start
        self._add_resource(
            mapper, controller_intance,
            path='/%s/online' % self.resource_name,
            put_action='online')

        return collection
