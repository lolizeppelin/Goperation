import routes
from simpleservice.wsgi import router

from goperation.manager.wsgi.port.routers import Routers as port_routes

mapper = routes.Mapper()

port_route = port_routes()
port_route.append_routers(mapper)

testing_route = router.ComposingRouter(mapper)

for x in  mapper.matchlist:
    print x.name

route_dict = mapper._routenames


for route_name in route_dict:
    print route_name, route_dict[route_name].conditions.get('method'),
    print route_dict[route_name].defaults.get('action'), route_dict[route_name].routepath

