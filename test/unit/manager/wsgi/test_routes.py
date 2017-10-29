import routes

from goperation.manager.wsgi.port.routers import Routers as port_routes
from goperation.manager.wsgi.file.routers import Routers as file_routes
from goperation.manager.wsgi.entity.routers import Routers as entity_routes
from goperation.manager.wsgi.endpoint.routers import Routers as endpoint_routes
from goperation.manager.wsgi.agent.routers import Routers as agent_routes
from goperation.manager.wsgi.asyncrequest.routers import Routers as async_routes


mapper = routes.Mapper()

for cls in (port_routes, file_routes, endpoint_routes, entity_routes, agent_routes, async_routes):
    r = cls()
    r.append_routers(mapper)

for x in  mapper.matchlist:
    # print x.method, x.action, x.routepath, x.regpath
    print  x.name, x.regpath, x.conditions
