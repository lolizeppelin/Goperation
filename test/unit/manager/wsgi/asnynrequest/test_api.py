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


for r in client.asyncs_index()['data']:
    print r

print client.async_show(request_id='0d23e9a7-ff10-4271-a252-d52b8efe524d')

# asyncs_index(self, body
# async_show(self, request_id, body)
# async_details(self, request_id, body)
# async_response(self, request_id, body)
# async_responses(self, request_id, body)
# async_overtime(self, request_id, body)