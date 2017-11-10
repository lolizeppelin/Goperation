from simpleservice.wsgi import router
from simpleservice.wsgi.middleware import controller_return_response

from goperation.manager.wsgi.asyncrequest import controller


MEMBER_ACTIONS = ['show', 'update']
COLLECTION_ACTIONS = ['index']


class Routers(router.RoutersBase):
    resource_name='asyncrequest'
    collection_name = resource_name + 's'

    def append_routers(self, mapper, routers=None):
        controller_intance = controller_return_response(controller.AsyncWorkRequest(),
                                                        controller.FAULT_MAP)
        collection = mapper.collection(collection_name=self.collection_name,
                                       resource_name=self.resource_name,
                                       controller=controller_intance,
                                       member_prefix='/{request_id}',
                                       collection_actions=COLLECTION_ACTIONS,
                                       member_actions=MEMBER_ACTIONS)
        # respone agents list
        collection.member.link('responses', method='GET')
        # get details of agent response
        collection.member.link('details', method='GET')
        # agent send respone data
        collection.member.link('respone', method='POST')
        # scheduler add overtime recode for overtime agent
        collection.member.link('overtime', method='PUT')
        return collection
