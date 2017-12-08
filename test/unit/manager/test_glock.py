import time
import simpleservice

from simpleutil.config import cfg
from goperation import config

from goperation.api.client import ManagerClient
import redis

a = 'C:\\Users\\loliz_000\\Desktop\\etc\\goperation\\goperation.conf'
b = 'C:\\Users\\loliz_000\\Desktop\\etc\\goperation\\gcenter.conf'
config.configure('test', [a, b])



from goperation.manager.api import  get_redis

rs = get_redis()

rs.set('test-key', 'wtf')

with rs.pipeline() as pipe:
    pipe.multi()
    pipe.sinter('test-key', 'a', 'b')
    pipe.sinter('test-key', 'a', 'b')
    try:
        result = pipe.execute()
    except Exception as e:
        print e.__class__.__name__
        print e.message

