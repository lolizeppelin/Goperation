from simpleservice.wsgi import router
from simpleservice.wsgi.middleware import controller_return_response

from goperation.manager.wsgi.agent.scheduler import controller
from goperation.manager import common as manager_common

MEMBER_ACTIONS = ['show', 'update', 'delete']
COLLECTION_ACTIONS = ['create']



class Routers(router.RoutersBase):

    resource_name = manager_common.SCHEDULER
    collection_name = resource_name + 's'

    def append_routers(self, mapper, routers=None):
        controller_intance = controller_return_response(controller.SchedulerRequest(),
                                                        controller.FAULT_MAP)
        collection = mapper.collection(collection_name=self.collection_name,
                                       resource_name=self.resource_name,
                                       controller=controller_intance,
                                       member_prefix='/{job_id}',
                                       collection_actions=COLLECTION_ACTIONS,
                                       member_actions=MEMBER_ACTIONS)
        collection.member.link('stop', method='POST')
        collection.member.link('start', method='POST')
        # return collection
