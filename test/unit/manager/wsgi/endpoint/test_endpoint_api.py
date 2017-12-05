import time
import simpleservice

from simpleutil.config import cfg
from goperation import config

from goperation.api.client import ManagerClient


a = 'C:\\Users\\loliz_000\\Desktop\\etc\\goperation\\goperation.conf'
b = 'C:\\Users\\loliz_000\\Desktop\\etc\\goperation\\gcenter.conf'
config.configure('test', [a, b])

wsgi_url = '172.31.0.110'
wsgi_port = 7999


client = ManagerClient(wsgi_url, wsgi_port)

print client.endpoints_index(agent_id=1)
print client.endpoints_show(agent_id=1, endpoint='gopcdn')
print client.endpoint_entitys(endpoint='gopcdn')
print client.endpoint_count(endpoints='gopcdn')

# endpoints_index(self, agent_id, body=None)
# endpoints_add(self, agent_id, endpoints)
# endpoints_show(self, agent_id, endpoint, body=None)
# endpoints_delete(self, agent_id, endpoint, body=None)
# endpoint_agents(self, endpoint)
# endpoint_entitys(self, endpoint)
# endpoint_count(self, endpoints)

