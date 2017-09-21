from simpleflow import api
from simpleflow.task import Task
from simpleflow.types import failure
from simpleflow.storage import Connection
from simpleflow.storage.middleware import LogBook

from goperation.taskflow import common


class StandardTask(Task):

    def __init__(self, middleware, provides=None, rebind=None):
        super(StandardTask, self).__init__(name='%s_%d' % (self.__class__.__name__,
                                                           middleware.entity),
                                           provides=provides,
                                           requires=None, auto_extract=True, rebind=rebind, inject=None,
                                           ignore_list=None, revert_rebind=None, revert_requires=None)
        self.middleware = middleware
        middleware.set_return(self.__class__.__name__)

    def revert(self, result, *args, **kwargs):
        if isinstance(result, failure.Failure):
            self.middleware.set_return(self.__class__.__name__, common.EXECUTE_FAIL)

    def post_execute(self):
        self.middleware.set_return(self.__class__.__name__, common.EXECUTE_SUCCESS)


class EntityTask(Task):

    def __init__(self, session, flow, store):
        super(EntityTask, self).__init__(name='engine_%s' % flow.name)
        self.book = LogBook(self.name)
        self.connection = Connection(session)
        self.engine = api.load(self.connection, flow, book=self.book, store=store)

    def execute(self, flow):
        try:
            self.engine.run()
        except Exception:
            pass
        finally:
            # cleanup sub taskflow engine logbook
            self.connection.destroy_logbook(self.book)


def format_store_rebind(store, rebind):
    for key in rebind:
        if key not in store:
            store[key] = None
