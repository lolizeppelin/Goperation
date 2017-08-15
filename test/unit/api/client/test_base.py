from goperation.api.client import base


from goperation.plugin.manager import common

host = 'surface'
local_ip = '127.0.0.1'
wsgi_url = '127.0.0.1'
wsgi_port = 7999



client = base.ManagerClient(host, local_ip, common.APPLICATION,
                            wsgi_url, wsgi_port)

def test_flush():
    print client.agent_flush()


def test_status():
    print client.agents_status(agent_id=1, body={'test': 1})

def test_active():
    print client.agent_active(agent_id=1, status=1)


test_active()