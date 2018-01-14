import time
import simpleservice

from simpleutil.config import cfg
from goperation import config

from goperation.api.client import ManagerClient

from simpleservice.plugin.exceptions import ServerExecuteRequestError


a = 'C:\\Users\\loliz_000\\Desktop\\etc\\goperation\\goperation.conf'
b = 'C:\\Users\\loliz_000\\Desktop\\etc\\goperation\\gcenter.conf'
config.configure('test', [a, b])


wsgi_url = '172.31.0.110'
wsgi_port = 7999


client = ManagerClient(wsgi_url, wsgi_port)


try:
    print client.file_show(file_id='517247dcab85b61087485498a409a707')
except ServerExecuteRequestError as e:
    print 'error'
    print e.resone


