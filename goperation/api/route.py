from simpleservice.wsgi import factory
from goperation import CORE_ROUTES
from goperation import EXTEND_ROUTES

app_factory = factory.app_factory(CORE_ROUTES + EXTEND_ROUTES)