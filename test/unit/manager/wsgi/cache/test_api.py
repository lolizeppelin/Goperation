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

print client.cache_flush()

# cache_flush(self, clean_online_key=False)
# cache_online(self, host, local_ip, agent_type)