from simpleutil.utils import uuidutils
from goperation.api.client import AgentManagerClient

from simpleservice.plugin.exceptions import AfterRequestError

from goperation.manager import exceptions

from goperation.manager import common

host = 'surface'
local_ip = '127.0.0.1'
wsgi_url = '127.0.0.1'
wsgi_port = 7999



client = AgentManagerClient(wsgi_url, wsgi_port,
                            host=host,
                            local_ip=local_ip,
                            agent_type=common.APPLICATION)

def test_cache():
    print client.cache_flush()
    print client.cache_online(client.host, client.local_ip, client.agent_type)


def test_file():
    print client.files_index()
    print client.file_show(uuidutils.generate_uuid())
    print client.file_delete(uuidutils.generate_uuid(), body={'force': False})
    print client.file_add(body={'wtf': 1})


def test_agent():
    # print client.agents_index()
    # print client.agent_show(2, body={'ports': True})
    print client.agent_create(body={'host': 'b.lolita.com',
                                    'agent_type': common.APPLICATION,
                                    'memory': 4096,
                                    'cpu': 16,
                                    'disk': 2048000,
                                    'ports_range': ['8000-9000'],
                                    'endpoints': ['mszl']
                                    })
    # print client.agent_delete(1, body={'force': True})
    # print client.agent_clean(1)

def test_endpoint():
    print client.endpoints_add(1, 'mszl')
    print client.endpoint_agents('mszl')
    print client.endpoint_entitys('mszl')
    # print client.endpoints_index(2)
    # print client.endpoints_show(2, 'mszl')


def test_entitys():
    # print client.entitys_show('mszl', '1')
    # print client.entitys_index('mszl')
    # try:
    #     print client.entitys_agent_index(1, 'mszl')
    # except AfterRequestError as e:
    #     print e.message
    #     print e.resone, e.code
    try:
        print client.entitys_add(1, 'mszl',
                                 body={'ports': [3303,3304]})
    except Exception as e:
        print e.message


def test_ports():
    print client.ports_index(1, 'mszl', 3)



# test_endpoint()
# test_agent()
# test_entitys()
test_ports()