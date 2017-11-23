import time
import simpleservice

from simpleutil.config import cfg
from goperation import config

from goperation.api.client import ManagerClient


a = 'C:\\Users\\loliz_000\\Desktop\\etc\\goperation\\goperation.conf'
b = 'C:\\Users\\loliz_000\\Desktop\\etc\\goperation\\gcenter.conf'
test_group = cfg.OptGroup(name='test')
config.configure(test_group, [a, b])

wsgi_url = '127.0.0.1'
wsgi_port = 7999


client = ManagerClient(wsgi_url, wsgi_port)


print client.ports_index(agent_id=1, endpoint='gopcdn', entity=1)



# ports_index(self, agent_id, endpoint, entity, body=None)
# ports_add(self, agent_id, endpoint, entity, body=None
# ports_delete(self, agent_id, endpoint, entity, ports, body=None)

