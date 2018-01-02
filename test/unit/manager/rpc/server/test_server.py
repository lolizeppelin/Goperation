import random
from simpleutil.config import cfg
from simpleutil.log import log as logging

from simpleservice.rpc.config import rpc_server_opts

from goperation import config as goperation_config

from goperation.manager.rpc.server.config import gop_rpc_server_opts
from goperation.manager.rpc.server import RpcServerManager

CONF = cfg.CONF
LOG = logging.getLogger(__name__)

def configure(config_files=None, config_dirs=None):
    # create a new project and group named gcenter
    name='gcenter'
    # init goperation config
    gcenter_group = goperation_config.configure(name, config_files, config_dirs)
    # set gcenter config
    CONF.register_opts(rpc_server_opts, group=gcenter_group)
    CONF.register_opts(gop_rpc_server_opts, group=gcenter_group)
    return CONF[gcenter_group.name]



def build_metadata(agent_id, extdata):

    _metadata = dict(zone='all',
                     host='test-%d' % agent_id,
                     agent_type="application",
                     external_ips=['test-ext-%d' % agent_id],
                     local_ip='test-local-%d' % agent_id,)
    _metadata.update(extdata)
    return _metadata


def build_agent(agent_id, extdata, extmetadata):


    disk = 5000 if random.randint(0, 1) else 10000

    loads = dict(cpu=4,
                memory=4000,
                disk=disk,
                free=2000,
                process=100,
                cputime=0,
                iowait=0,
                left=5000,
                metadata=build_metadata(agent_id, extmetadata),
                )

    loads.update(extdata)
    return loads


def build_database_agent(agent_id):
    extmetadata = {'mysql': '5.6.0'}
    extdata = {'free': random.randint(1500, 2500),
               'iowait': random.randint(0, 30),
               'cputime': random.randint(0, 30),
               'left': random.randint(3800, 4700),
               }
    return build_agent(agent_id, extdata, extmetadata)

def build_game_agent(agent_id):
    extdata = {'free': random.randint(1000, 2000),
               'iowait': random.randint(0, 5),
               'cputime': random.randint(0, 30),
               'left': random.randint(3800, 4700),
               }
    return build_agent(agent_id, extdata, extmetadata={})


def build_test_agent():
    agents = {}
    for i in range(1, 30):
        agents[i] = build_database_agent(i)
    for i in range(30, 60):
        agents[i] = build_game_agent(i)

    return agents




def main():
    a = 'C:\\Users\\loliz_000\\Desktop\\etc\\goperation\\goperation.conf'
    b = 'C:\\Users\\loliz_000\\Desktop\\etc\\goperation\\agent.conf'
    c = 'C:\\Users\\loliz_000\\Desktop\\etc\\goperation\\endpoints'
    configure([a, b], config_dirs=c)
    rpcmanager = RpcServerManager()
    rpcmanager.agents_loads = build_test_agent()
    # for agent_id in rpcmanager.agents_loads:
    #     print agent_id, rpcmanager.agents_loads[agent_id]

    chioces = rpcmanager.agents_loads.keys()


    includes = ['metadata.zone=%s' % 'all',
                'metadata.mysql!=None',
                'metadata.mysql>=5.5',
                'disk>=%d' % 10000, 'free>=%d' % 2000, 'cpu>=%d' % 4]

    weighters = [{'iowait': 3},
                 {'cputime': 5},
                 {'free': 200},
                 {'cpu': -1},
                 {'left': -300},
                 {'process': None}]

    rpcmanager._exclud_filter(includes, chioces)

    rpcmanager._sort_by_weigher(weighters, chioces)

    for agent_id in  chioces:
        print agent_id, rpcmanager.agents_loads[agent_id]




if __name__ == '__main__':
    main()
