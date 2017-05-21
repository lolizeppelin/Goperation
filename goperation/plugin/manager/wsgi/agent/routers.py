from simpleservice.wsgi import router

MEMBER_ACTIONS = ['show']
COLLECTION_ACTIONS = ['index']


class Routers(router.RoutersBase):
    collection_name = 'agents'
    resource_name='agent'