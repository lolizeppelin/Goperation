import webob.exc


from simpleutil.utils import argutils
from simpleutil.utils import timeutils
from simpleutil.utils import uuidutils
from simpleutil.utils import jsonutils

from simpleutil.utils.attributes import validators

from simpleutil.common.exceptions import InvalidArgument

from simpleservice.ormdb.api import model_query

from goperation.plugin.manager import common as manager_common

from goperation.plugin.manager.models import Agent

from goperation.plugin.manager.wsgi import contorller
from goperation.plugin.manager.wsgi import resultutils
from goperation.plugin.manager.dbapi import get_session



FAULT_MAP = {InvalidArgument: webob.exc.HTTPClientError}

Idformater = argutils.Idformater(key='agent_id', all_key="all", formatfunc=int)

class AgentReuest(contorller.BaseContorller):

    def _all_id(self):
        session = get_session(readonly=True)
        query = model_query(session, Agent)(Agent.agent_id).all()
        results = query(Agent.agent_id).all()
        for result in results:
            print type(result)
            print result
        id_set = set()
        return id_set

    def index(self, req, body):
        self._all_id()

    argutils.Idformater(key='agent_id', formatfunc=int)
    def show(self, req, agent_id, body):
        return 'show'

    argutils.Idformater(key='host')
    def create(self, req, host, body):
        new_agent = Agent()
        try:
            new_agent.host = validators['type:hostname'](host.pop())
            new_agent.agent_type = body.pop('agent_type')
            if len(new_agent.agent_type) > 64:
                raise ValueError('Agent type info over size')
            new_agent.ports_range = jsonutils.dumps(validators['type:ports_range_list'](body.pop('ports_range')))
            if len(new_agent.ports_range) > manager_common.MAX_PORTS_RANGE_SIZE:
                raise ValueError('Ports range info over size')
            new_agent.memory = int(body.pop('memory'))
            new_agent.cpu = int(body.pop('cpu'))
            new_agent.disk = int(body.pop('disk'))
        except KeyError as e:
            raise InvalidArgument('Can not find value: %s' % e.message)
        except ValueError as e:
            raise InvalidArgument('Value type error: %s' % e.message)
        new_agent.create_time = timeutils.realnow()
        new_agent.entiy = 0
        session = get_session()
        session.add(new_agent)
        session.flush()
        result = resultutils.results(total=1, pagenum=0, msg='Create agent success')
        result['data'].append(dict(agent_id=new_agent.agent_id,
                                   host=new_agent.host,
                                   ports_range=new_agent.ports_range,
                                   ))
        return result

    argutils.Idformater(key='agent_id', formatfunc=int, all_key='all')
    def sendfile(self, req, agent_id, body):
        pass
