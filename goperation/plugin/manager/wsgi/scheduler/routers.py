from simpleservice.wsgi import router

MEMBER_ACTIONS = ['show']
COLLECTION_ACTIONS = ['index']


class Routers(router.RoutersBase):
    collection_name = 'schdulers'
    resource_name='schduler'

    pass