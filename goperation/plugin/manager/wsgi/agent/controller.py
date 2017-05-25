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

from goperation.plugin.manager.wsgi import contorller
from goperation.plugin.manager.wsgi import resultutils
from goperation.plugin.manager.dbapi import get_session
from goperation.plugin.manager.dbapi import get_glock

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
        results = query.all()
        for result in results:
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
        agent = query.filter_by(agent_id=agent_id).first()
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

    def create(self, req, body):
        """call bay agent"""
        lock = get_glock()
        new_agent = Agent()
        try:
            new_agent.host = validators['type:hostname'](body.pop('host'))
            new_agent.agent_type = body.pop('agent_type')
            if len(new_agent.agent_type) > 64:
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
        with lock(key='Agent', locktime=60, alloctime=0.3):
            host_filter = and_(Agent.host == new_agent.host, Agent.status > manager_common.DELETED)
            if model_count_with_key(session, Agent.host, filter=host_filter) > 0:
                raise InvalidArgument('Duplicate host exist')
            new_agent_id = model_autoincrement_id(session, Agent.agent_id)
            new_agent.agent_id = new_agent_id
            session.add(new_agent)
            session.flush()
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
        lock = get_glock()
        session = get_session(readonly=True)
        query = model_query(session, Agent, filter=and_(Agent.agent_id == agent_id,
                                                        Agent.status > manager_common.DELETED))
        data = {}
        with lock(key='Agent', locktime=60, alloctime=0.3):
            if len(agent_id) < model_count_with_key(session, Agent.host,
                                                    filter=(Agent.status > manager_common.DELETED)):
                 query = query.filter(Agent.agent_id.in_(agent_id))
            query.update(data)
        result = resultutils.results(total=len(agent_id), pagenum=0,
                                     msg='Update agent success',
                                     data=[body, ])
        return result

    @Idformater
    def upgrade(self, req, agent_id, body):
        """call by client, and asyncrequest"""
        # TODO need redis global lock
        self.create_request(req, body)
        session = get_session(readonly=True)
        query = model_query(session, Agent).filter(Agent.status > manager_common.DELETED)
        if len(agent_id) < self.all_id:
             query = query.filter(Agent.agent_id.in_(agent_id))
        agents = query.filter(Agent.agent_id.in_(agent_id)).all()
        return {'msg': 'upgrade', 'data': agent_id}

    @argutils.Idformater(key='agent_id', formatfunc=int)
    def delete(self, agent_id, body):
        """call buy client"""
        if len(agent_id) != 1:
            raise InvalidArgument('Agent delete just for one agent')
        agent_id = agent_id.pop()
        lock = get_glock()
        session = get_session(readonly=True)
        query = model_query(session, Agent,
                            filter=and_(Agent.agent_id == agent_id,
                                        Agent.status > manager_common.DELETED))
        with lock(key='Agent', locktime=60, alloctime=0.3):
            agent = query.one_or_none()
            if not agent:
                raise InvalidArgument('Can not find agent with %d, not exist or alreay deleted' % agent_id)
            if agent.entiy > 0:
                raise InvalidArgument('Can not delete agent, entiy not 0')
            agent.update({'status': manager_common.DELETED})
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
