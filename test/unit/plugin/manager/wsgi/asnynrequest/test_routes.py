import routes
from simpleservice.wsgi import router

from goperation.plugin.manager.wsgi.asyncrequest.routers import Routers as async_routes

mapper = routes.Mapper()

async_routes = async_routes()
async_routes.append_routers(mapper)

testing_route = router.ComposingRouter(mapper)

for x in  mapper.matchlist:
    print x.name

route_dict = mapper._routenames


for route_name in route_dict:
    print route_name, route_dict[route_name].conditions.get('method'),
    print route_dict[route_name].defaults.get('action'), route_dict[route_name].routepath
