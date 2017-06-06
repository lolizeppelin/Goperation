from simpleutil.utils import jsonutils

import requests
from requests.sessions import Session

from goperation.plugin.manager import common
import time

version = "v1.0"

resource = 'agent'
collection = '%(resource)ss' % {'resource': resource}

ip = '127.0.0.1'
port = 7999


# url index
resource_url = """http://%(dst)s:%(port)s/%(version)s/%(resource)s""" % \
            {'dst': ip,
             'port':port,
             'version': version,
             'resource': resource}

collection_url = """http://%(dst)s:%(port)s/%(version)s/%(collection)s""" % \
            {'dst': ip,
             'port':port,
             'version': version,
             'collection': collection}


def index_test():
    session = Session()
    # res = requests.post(base_url, json={'id':1)
    res = requests.get(collection_url, json={'async': True, 'test':'wtf'})
    print 'statu code is', res.status_code
    try:
        data = jsonutils.loads(res.text)
        print data['msg']
        for row in data['data']:
            print row
    except:
        print 'json load fail'
        print res.text
    session.close()

def create_test():
    session = Session()



    create_data = {
                   'host': 'agentserver',
                   'agent_type': common.APPLICATION,
                   'memory': 100,
                   'cpu': 16,
                   'disk': 100,
                   'endpoints': ['mszl'],
                   'ports_range': ['2-5', '6-7', '7-8']
                   }

    res = requests.post(collection_url, json=create_data)
    print 'statu code is', res.status_code
    print res.text
    session.close()

def show_test(agent_id):
    session = Session()
    url = collection_url + '/%s' % str(agent_id)
    print url
    res = requests.get(url,
                       json={'async': True})
    print 'statu code is', res.status_code
    print res.text
    session.close()

def update_test():
    session = Session()
    url = collection_url + '/all'
    print url
    res = requests.put(url,
                       json={'status': 1, 'async_checker': 1})
    print 'statu code is', res.status_code
    print res.text
    session.close()

def upgrade_test():
    session = Session()
    url = collection_url + '/all/upgrade'
    print url
    res = requests.post(url,
                       json={'status': 1, 'async_checker': 1,
                             'request_time': time.time(),
                             })
    print 'statu code is', res.status_code
    print res.text
    session.close()

def online_test():
    session = Session()
    url = resource_url + '/online'
    print url
    res = requests.put(url,
                       json={'host': 'newh43ost',
                             'agent_type': common.APPLICATION,
                             'agent_ipaddr': '172.20.0.1'
                             })
    print 'statu code is', res.status_code
    print res.text
    session.close()


def active_test():
    session = Session()
    url = collection_url + '/all/active'
    print url
    res = requests.put(url,
                       json={'status': 1, 'async_checker': 1,
                             'request_time': time.time(),
                             })
    print 'statu code is', res.status_code
    print res.text
    session.close()


# print '\nindex test-----------'
# index_test()
# print '\nshow test-----------'
# show_test('1')
# print '\nupdate test-----------'
# update_test()
# print '\ncreate test-----------'
# create_test()
# print '\nupgrade test-----------'
# upgrade_test()
# print '\nactive test-----------'
# active_test()
print '\nonline test-----------'
online_test()
