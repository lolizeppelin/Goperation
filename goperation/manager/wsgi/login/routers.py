from simpleservice.wsgi import router
from simpleservice.wsgi.middleware import controller_return_response

from goperation.manager.wsgi.login import controller
from goperation.manager import common as manager_common

COLLECTION_ACTIONS = []
MEMBER_ACTIONS = []


class Routers(router.RoutersBase):
    # resource_name = manager_common.LOGIN
    # collection_name = resource_name + 's'

    def append_routers(self, mapper, routers=None):
        controller_intance = controller_return_response(controller.LoginReuest(), controller.FAULT_MAP)
        self._add_resource(mapper, controller_intance, path='/{username}', post_action='login')
        self._add_resource(mapper, controller_intance, path='/{username}', delete_action='loginout')
