from simpleservice.wsgi import factory
from goperation.plugin import CORE_ROUTES
from goperation.plugin import EXTEND_ROUTES

app_factory = factory.app_factory(CORE_ROUTES + EXTEND_ROUTES)