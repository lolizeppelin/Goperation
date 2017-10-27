from goperation import CORE_ROUTES
from goperation.manager.wsgi.asyncrequest import routers as request_routes
from goperation.manager.wsgi.agent import routers as agent_routes
from goperation.manager.wsgi.file import routers as file_routes
from goperation.manager.wsgi.port import routers as port_routes
from goperation.manager.wsgi.endpoint import routers as endpoint_routes
from goperation.manager.wsgi.entity import routers as entity_routes


from goperation.manager.wsgi.agent.scheduler import routers as scheduler_routes
from goperation.manager.wsgi.agent.application import routers as application_routes

CORE_ROUTES.extend([request_routes, agent_routes,
                    file_routes, port_routes, endpoint_routes, entity_routes,
                    scheduler_routes, application_routes])
