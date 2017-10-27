import routes

from simpleutil.utils import uuidutils

from simpleservice.wsgi import router
from simpleservice.wsgi.middleware import controller_return_response


MEMBER_ACTIONS = ['show']
COLLECTION_ACTIONS = []

class Contorller(object):

    def show(self, req, mark):
        print req.params
        print mark
        data = {'downloader': 'http',
                'address': 'http://127.0.0.1/wtf.zip',
                'ext': 'zip',
                'size': 4096,
                'uploadtime': '2010-11-10 11:11:10',
                'marks': {'uuid': uuidutils.generate_uuid(),
                          'crc32': 'e3fb18f2',
                          'md5': 'aa9aca6939589fba87b0d9710f2a4f8c'},
                }
        return data


class Routers(router.RoutersBase):
    resource_name='file'
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
