from simpleflow import api
from simpleflow.task import Task
from simpleflow.types import failure
from simpleflow.storage import Connection
from simpleflow.storage.middleware import LogBook
from simpleflow.engines.engine import ParallelActionEngine

from goperation.taskflow import common


class StandardTask(Task):

    @property
    def taskname(self):
        return self.__class__.__name__


    def __init__(self, middleware, provides=None,
                 rebind=None, requires=None,
                 revert_rebind=None, revert_requires=None):
        self.middleware = middleware
        middleware.set_return(self.taskname)
        super(StandardTask, self).__init__(name='%s_%d' % (self.taskname,  middleware.entity),
                                           provides=provides,
                                           rebind=rebind, requires=requires,
                                           revert_rebind=revert_rebind, revert_requires=revert_requires)

    def revert(self, *args, **kwargs):
        result = kwargs.get('result') if 'result' in kwargs else args[0]
        if isinstance(result, failure.Failure):
            self.middleware.set_return(self.taskname, common.EXECUTE_FAIL)

    def post_execute(self):
        self.middleware.set_return(self.taskname, common.EXECUTE_SUCCESS)


class EntityTask(Task):

    def __init__(self, session, flow, store):
        super(EntityTask, self).__init__(name='engine_%s' % flow.name)
        book = LogBook(self.name)
        self.book_uuid = book.uuid
        self.connection = Connection(session)
        self.engine = api.load(self.connection, flow, book=book, store=store,
                               engine_cls=ParallelActionEngine)

    def execute(self):
        try:
            self.engine.run()
        finally:
            # cleanup sub taskflow engine logbook
            self.connection.destroy_logbook(self.book_uuid)


def format_store_rebind(store, rebind):
    for key in rebind:
        if key not in store:
            store[key] = None
