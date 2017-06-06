from goperation.plugin.manager.wsgi.agent import routers as agent_routes
from goperation.plugin.manager.wsgi.agent.scheduler import routers as scheduler_routes
from goperation.plugin.manager.wsgi.agent.application import routers as application_routes
from goperation.plugin.manager.wsgi.asyncrequest import routers as request_routes

from goperation import plugin

plugin.CORE_ROUTES.extend([request_routes, agent_routes, scheduler_routes, application_routes])
