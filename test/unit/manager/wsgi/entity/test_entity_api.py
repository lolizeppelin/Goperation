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


# print client.entitys_index(endpoint='gopcdn')
# print client.entitys_agent_index(agent_id=1, endpoint='gopcdn')
# try:
#     print client.entitys_show(endpoint='gopcdn', entitys=1)
# except Exception as e:
#     print e
# try:
#     print client.entitys_add(agent_id=1, endpoint='gopcdn',
#                              body={'forendpoint': 'mszl', 'etype': 'ios',
#                                    'uri': 'http://172.23.0.2:8081/svn/pokemon_assets_online/default.ios',
#                                    'auth': {'username': 'pokemon_op_manager',
#                                             'password': '0bcc3acb7431f3d0'}})
# except Exception as e:
#     print e

# try:
#     result = client.entity_logs(endpoint='gopcdn', entity=3)
# except Exception as e:
#     print e.resone
#     raise
# if result.get('resultcode') != 0:
#     raise
#
# print result
#
# uri = result.get('data')[0]

from websocket import create_connection

try:
    print int(time.time())
    ws = create_connection("ws://%s:%d/checkout.1520919566.cdnresource.22.1.log" % ('172.31.0.126', 5000),
                           subprotocols=["binary"])
    print int(time.time())
except Exception:
    print 'wtf?'
    raise

while True:
    r = ws.recv()
    print int(time.time())
    if r:
        print r
    else:
        break



# print client.entitys_show(endpoint='gopcdn', entitys=3)
# entitys_index = endpoint_entitys
# entitys_agent_index(self, agent_id, endpoint, body=None)
# entitys_add(self, agent_id, endpoint, body)
# entitys_show(self, endpoint, entitys, body=None)
# entitys_delete(self, endpoint, entitys, body=None
