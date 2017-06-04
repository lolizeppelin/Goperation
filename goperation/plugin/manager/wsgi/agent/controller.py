import webob.exc

from sqlalchemy import func
from sqlalchemy.sql import or_
from sqlalchemy.sql import and_

from simpleutil.utils import argutils
from simpleutil.utils import timeutils
from simpleutil.utils import jsonutils

from simpleutil.log import log as logging

from simpleutil.utils.attributes import validators

from simpleutil.common.exceptions import InvalidArgument

from simpleservice.ormdb.api import model_query
from simpleservice.ormdb.api import model_count_with_key
from simpleservice.ormdb.api import model_autoincrement_id

from goperation.plugin import utils

from goperation.plugin.manager import common as manager_common

from goperation.plugin.manager.models import Agent
from goperation.plugin.manager.models import AgentEndpoint

from goperation.plugin.manager import targetutils
from goperation.plugin.manager.wsgi import contorller
from goperation.plugin.manager.wsgi import resultutils
from goperation.plugin.manager.api import get_session
from goperation.plugin.manager.api import mlock
from goperation.plugin.manager.api import get_client


from sqlalchemy.exc import OperationalError
from simpleservice.ormdb.exceptions import DBError

LOG = logging.getLogger(__name__)

FAULT_MAP = {InvalidArgument: webob.exc.HTTPClientError,
             }

Idformater = argutils.Idformater(key='agent_id', all_key="all", formatfunc=int)


class AgentReuest(contorller.BaseContorller):

    def _all_id(self):
        id_set = set()
        session = get_session(readonly=True)
        query = session.query(Agent.agent_id).filter(Agent.status > manager_common.DELETED)
        # results = query.all()
        # for result in results:
        for result in query:
            id_set.add(result[0])
        return id_set

    def index(self, req, body):
        """call buy client"""
        session = get_session(readonly=True)
        rows_num = model_count_with_key(session, Agent.agent_id)
        self._all_id()
        return rows_num

    @argutils.Idformater(key='agent_id', formatfunc=int)
    def show(self, req, agent_id, body):
        """call buy client"""
        if len(agent_id) != 1:
            raise InvalidArgument('Agent show just for one agent')
        agent_id = agent_id.pop()
        session = get_session(readonly=True)
        query = model_query(session, Agent)
        agent = query.filter_by(agent_id=agent_id).one_or_none()
        if not agent:
            raise InvalidArgument('Agent_id id:%s can not be found' % agent_id)
        result = resultutils.results(total=1, pagenum=0, msg='Create agent success')
        result['data'].append(dict(agent_id=agent.agent_id,
                                   host=agent.host,
                                   status=agent.status,
                                   ports_range=agent.ports_range,
                                   endpoints=[v['endpoint'] for v in agent.endpoints],
                                   ))
        return result

    @argutils.Idformater(key='agent_id', formatfunc=int)
    def register(self, req, agent_id, body):
        """call buy client"""
        if len(agent_id) != 1:
            raise InvalidArgument('Agent register just for one agent')
        agent_id = agent_id.pop()
        agent_type = body.pop('agent_type')
        session = get_session(readonly=True)
        query = model_query(session, Agent)
        agent = query.filter_by(agent_id=agent_id).one_or_none()
        if not agent:
            ret = {}
        else:
            ret = {}
        result = resultutils.results(total=1, pagenum=0, msg='Register agent function run success')
        result['data'].append(ret)
        return result

    def create(self, req, body):
        """call bay agent"""
        new_agent = Agent()
        try:
            new_agent.host = validators['type:hostname'](body.pop('host'))
            new_agent.agent_type = body.pop('agent_type', None)
            if new_agent.agent_type is None or len(new_agent.agent_type) > 64:
                raise ValueError('Agent type info over size')
            new_agent.ports_range = jsonutils.dumps(validators['type:ports_range_list'](body.pop('ports_range')))
            if len(new_agent.ports_range) > manager_common.MAX_PORTS_RANGE_SIZE:
                raise ValueError('Ports range info over size')
            new_agent.memory = int(body.pop('memory'))
            new_agent.cpu = int(body.pop('cpu'))
            new_agent.disk = int(body.pop('disk'))
            endpoints = utils.validate_endpoints(body.pop('endpoints', []))
        except KeyError as e:
            raise InvalidArgument('Can not find argument: %s' % e.message)
        except ValueError as e:
            raise InvalidArgument('Argument value type error: %s' % e.message)
        new_agent.create_time = timeutils.realnow()
        new_agent.entiy = 0
        if endpoints:
            endpoints_entitys = []
            for endpoint in endpoints:
                endpoints_entitys.append(AgentEndpoint(endpoint=endpoint))
            new_agent.endpoints = endpoints_entitys
        session = get_session()
        with mlock(targetutils.lock_all_agent):
            host_filter = and_(Agent.host == new_agent.host, Agent.status > manager_common.DELETED)
            if model_count_with_key(session, Agent.host, filter=host_filter) > 0:
                raise InvalidArgument('Duplicate host %s exist' % new_agent.host)
            with session.begin(subtransactions=True):
                new_agent_id = model_autoincrement_id(session, Agent.agent_id)
                new_agent.agent_id = new_agent_id
                session.add(new_agent)
                result = resultutils.results(total=1, pagenum=0, msg='Create agent success',
                                             data=[dict(agent_id=new_agent.agent_id,
                                                        host=new_agent.host,
                                                        status=new_agent.status,
                                                        ports_range=new_agent.ports_range,
                                                        endpoints=endpoints)
                                                   ])
                return result

    @Idformater
    def file(self, req, agent_id, body):
        """call by client, and asyncrequest"""
        pass

    @Idformater
    def update(self, req, agent_id, body):
        """call by agent"""
        session = get_session(readonly=True)
        with mlock(targetutils.lock_all_agent) as lock:
            query = model_query(session, Agent, filter=(Agent.status > manager_common.DELETED))
            if len(agent_id) < len(self.all_id):
                query = query.filter(Agent.agent_id.in_(agent_id))
                # degrade lock level
                lock.degrade([targetutils.AgentLock(_id) for _id in agent_id])
            data = {}
            with session.begin(subtransactions=True):
                # TODO rpc call update
                query.update(data)
            result = resultutils.results(total=len(agent_id), pagenum=0,
                                         msg='Update agent success',
                                         data=[body, ])
            return result

    @Idformater
    def upgrade(self, req, agent_id, body):
        """call by client, and asyncrequest"""
        self.create_request(req, body)
        session = get_session(readonly=True)
        with mlock(targetutils.lock_all_agent) as lock:
            query = model_query(session, Agent).filter(Agent.status > manager_common.DELETED)
            if len(agent_id) < len(self.all_id):
                query = query.filter(Agent.agent_id.in_(agent_id))
                lock.degrade([targetutils.AgentLock(_id) for _id in agent_id])
            # agents = query.all()
        return {'msg': 'upgrade', 'data': agent_id}

    @argutils.Idformater(key='agent_id', formatfunc=int)
    def delete(self, agent_id, body):
        """call buy client"""
        if len(agent_id) != 1:
            raise InvalidArgument('Agent delete just for one agent')
        agent_id = agent_id.pop()
        rpc = get_client()
        session = get_session(readonly=True)
        query = model_query(session, Agent,
                            filter=and_(Agent.agent_id == agent_id,
                                        Agent.status > manager_common.DELETED))
        with mlock(targetutils.AgentLock(agent_id)):
            with session.begin(subtransactions=True):
                agent = query.one_or_none()
                if not agent:
                    raise InvalidArgument('Can not find agent with %d, not exist or alreay deleted' % agent_id)
                if agent.entiy > 0:
                    raise InvalidArgument('Can not delete agent, entiy not 0')
                # TODO rpc call delete!
                rpc_ret = rpc.call(targetutils.target_agent(agent),
                                   )
                query.update({'status': manager_common.DELETED})
                msg = 'Delete agent success'
                query = model_query(session, AgentEndpoint,
                                    filter=AgentEndpoint.agent_id == agent_id)
                try:
                    query.delete()
                except (OperationalError, DBError) as e:
                    LOG.error("Delete agent endpoint error:%d, %s" %
                              (e.orig[0], e.orig[1].replace("'", '')))
                    msg += ' delete endpoint OperationalError'
                except DBError as e:
                    LOG.error("Delete agent endpoint DBError:%s" % e.message)
                    msg += ' delete endpoint DBError'
                result = resultutils.results(total=1, pagenum=0, msg=msg,
                                             data=[dict(agent_id=agent.agent_id,
                                                        host=agent.host,
                                                        status=agent.status,
                                                        ports_range=agent.ports_range)
                                                   ])
                return result
