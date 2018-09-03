from simpleservice.wsgi import factory
from goperation import CORE_ROUTES
from goperation import EXTEND_ROUTES
from goperation import OPEN_ROUTES

private_factory = factory.app_factory(CORE_ROUTES + EXTEND_ROUTES)
public_factory = factory.app_factory(OPEN_ROUTES)
