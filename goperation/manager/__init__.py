from goperation import CORE_ROUTES
from goperation.manager.wsgi.asyncrequest import routers as request_routes
from goperation.manager.wsgi.agent import routers as agent_routes
from goperation.manager.wsgi.agent.scheduler import routers as scheduler_routes
from goperation.manager.wsgi.agent.application import routers as application_routes

CORE_ROUTES.extend([request_routes, agent_routes, scheduler_routes, application_routes])
