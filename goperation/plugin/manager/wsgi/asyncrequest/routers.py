from simpleservice.wsgi import router
from simpleservice.wsgi.middleware import controller_return_response

from goperation.plugin.manager.wsgi.asyncrequest import controller


MEMBER_ACTIONS = ['show', 'update']
COLLECTION_ACTIONS = ['index']


class Routers(router.RoutersBase):
    resource_name='asyncrequest'
    collection_name = resource_name + 's'

    def append_routers(self, mapper, routers):
        controller_intance = controller_return_response(controller.AsyncWorkRequest(),
                                                        controller.FAULT_MAP)
        collection = mapper.collection(collection_name=self.collection_name,
                                       resource_name=self.resource_name,
                                       controller=controller_intance,
                                       member_prefix='/{request_id}',
                                       collection_actions=COLLECTION_ACTIONS,
                                       member_actions=MEMBER_ACTIONS)
        # collection.member.link(rel='active', action='active', method='POST')
        return collection