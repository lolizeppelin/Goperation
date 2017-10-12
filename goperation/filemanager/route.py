import routes
from simpleservice.wsgi import router
from simpleservice.wsgi.middleware import controller_return_response


MEMBER_ACTIONS = ['show']
COLLECTION_ACTIONS = []

class Contorller(object):

    def show(self, req, mark):
        print 'get mark'


class Routers(router.RoutersBase):
    resource_name='filemanager'
    collection_name = resource_name + 's'

    def append_routers(self, mapper, routers=None):
        controller_intance = controller_return_response(Contorller())
        collection = mapper.collection(collection_name=self.collection_name,
                                       resource_name=self.resource_name,
                                       controller=controller_intance,
                                       member_prefix='/{mark}',
                                       collection_actions=COLLECTION_ACTIONS,
                                       member_actions=MEMBER_ACTIONS)
        collection.member.link('files', method='GET')
        return collection


def app_factory(global_conf, **local_conf):
    mapper = routes.Mapper()
    sub_routers = []
    r = Routers()
    r.append_routers(mapper, sub_routers)
    return router.ComposingRouter(mapper, sub_routers)
