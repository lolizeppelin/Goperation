import time
import simpleservice

from simpleutil.config import cfg
from goperation import config
import requests

from simpleservice.plugin.exceptions import ClientRequestError

from goperation.api.client import ManagerClient


a = 'C:\\Users\\loliz_000\\Desktop\\etc\\goperation\\goperation.conf'
b = 'C:\\Users\\loliz_000\\Desktop\\etc\\goperation\\gcenter.conf'
config.configure('test', [a, b])



wsgi_url = '172.31.0.110'
# wsgi_url = '127.0.0.1'
wsgi_port = 7999

session = requests.Session()
client = ManagerClient(wsgi_url, wsgi_port, session=session)

try:
    print client.agents_index()
except ClientRequestError as e:
    print e.message
    print e.code
    print e.resone
# print client.agent_show(agent_id=1)['data']
# print client.agents_status(agent_id=1, body={'request_time': int(time.time())})
# print client.agent_active(agent_id=1, status=1)['data']
# print client.agent_logs(agent_id=1)
# print client.agents_upgrade(agent_id='all', body={'request_time': int(time.time())})


import time

time.sleep(50)
print client.agents_index()

# agent_create(self, body)
# agents_index(self, body=None)
# agent_delete(self, agent_id, body)
# agent_show(self, agent_id, body=None)
# agents_update(self, agent_id, body)
# agents_status(self, agent_id, body)
# agent_edit(self, agent_id, body)
# agent_active(self, agent_id, status)
# agents_upgrade(self, agent_id, body)
# agent_report(self, agent_id, body)