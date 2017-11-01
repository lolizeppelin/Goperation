from goperation import CORE_ROUTES
from goperation import EXTEND_ROUTES
from goperation.manager.wsgi.agent import routers as agent_routes
from goperation.manager.wsgi.file import routers as file_routes
from goperation.manager.wsgi.port import routers as port_routes
from goperation.manager.wsgi.endpoint import routers as endpoint_routes
from goperation.manager.wsgi.entity import routers as entity_routes
from goperation.manager.wsgi.cache import routers as cache_routes
from goperation.manager.wsgi.asyncrequest import routers as asyncrequest_routes
from goperation.manager.wsgi.agent.scheduler import routers as scheduler_routes
from goperation.manager.wsgi.agent.application import routers as application_routes

CORE_ROUTES.extend([port_routes, entity_routes, endpoint_routes, agent_routes,
                    scheduler_routes, application_routes, asyncrequest_routes,
                    cache_routes])

EXTEND_ROUTES.extend([file_routes, ])