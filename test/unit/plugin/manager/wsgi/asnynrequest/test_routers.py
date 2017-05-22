from simpleutil.utils import jsonutils

import requests
from requests.sessions import Session

version = "v1.0"

resource = 'asyncrequest'
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
    # res = requests.post(base_url, json={'id':1)
    res = requests.post(collection_url, json={'async': True})
    print 'statu code is', res.status_code
    print res.text
    session.close()


def show_test(request_id):
    session = Session()
    url = collection_url + '/%s' % str(request_id)
    print url
    res = requests.get(url,
                       json={'async': True})
    print 'statu code is', res.status_code
    print res.text
    session.close()

print 'index test-----------\n'

index_test()

print 'show test-----------\n'

show_test('da01ec14-159b-488f-be36-5a0558dad937')


def update_test(request_id):
    session = Session()
    url = collection_url + '/%s' % str(request_id)
    print url
    res = requests.put(url,
                       json={'status': 1, 'async_checker': 1})
    print 'statu code is', res.status_code
    print res.text
    session.close()


print 'update test-----------\n'

update_test('8dee8ec1-83a9-4d8e-b2dc-c6bdf345f13e')