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


print client.entitys_index(endpoint='gopcdn')
print client.entitys_agent_index(agent_id=1, endpoint='gopcdn')
try:
    print client.entitys_show(endpoint='gopcdn', entitys=1)
except Exception as e:
    print e
try:
    print client.entitys_add(agent_id=1, endpoint='gopcdn', body=None)
except Exception as e:
    print e


# entitys_index = endpoint_entitys
# entitys_agent_index(self, agent_id, endpoint, body=None)
# entitys_add(self, agent_id, endpoint, body)
# entitys_show(self, endpoint, entitys, body=None)
# entitys_delete(self, endpoint, entitys, body=None
