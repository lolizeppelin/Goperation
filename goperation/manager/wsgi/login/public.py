from simpleservice.wsgi import router
from simpleservice.wsgi.middleware import controller_return_response

# from goperation.manager import common as manager_common
from goperation.manager.wsgi.login import controller

COLLECTION_ACTIONS = []
MEMBER_ACTIONS = []


class Routers(router.RoutersBase):

    resource_name = 'goplogin'
    # collection_name = resource_name + 's'

    def append_routers(self, mapper, routers=None):
        controller_intance = controller_return_response(controller.LoginApiRequest(), controller.FAULT_MAP)
        self._add_resource(mapper, controller_intance, path='/goperation/login/{username}',
                           post_action='login')

        # mapper.collection(collection_name=self.collection_name,
        #                   resource_name=self.resource_name,
        #                   controller=controller_intance,
        #                   collection_actions=COLLECTION_ACTIONS,
        #                   member_actions=MEMBER_ACTIONS)
