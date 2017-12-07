import time
import eventlet
import contextlib

from sqlalchemy.sql import and_

from redis.exceptions import ConnectionError
from redis.exceptions import TimeoutError
from redis.exceptions import WatchError
from redis.exceptions import ResponseError

from simpleutil.config import cfg
from simpleutil.utils import timeutils
from simpleutil.utils import uuidutils
from simpleutil.utils import jsonutils
from simpleutil.utils import argutils
from simpleutil.utils.attributes import validators
from simpleutil.log import log as logging
from simpleutil.common.exceptions import InvalidArgument

from simpleservice.ormdb.api import model_query
from simpleservice.ormdb.api import model_count_with_key
from simpleservice.ormdb.api import model_autoincrement_id


from goperation.manager import exceptions
from goperation.manager import common as manager_common
from goperation.manager.config import manager_group
from goperation.manager.models import Agent
from goperation.manager.models import AgentEndpoint
from goperation.manager.models import AgentEntity
from goperation.manager.utils import validateutils


LOG = logging.getLogger(__name__)

CONF = cfg.CONF


class GlobalData(object):

    PREFIX = CONF[manager_group.name].redis_key_prefix
    AGENT_KEY = '-'.join([PREFIX, manager_common.AGENT])
    # AGENTS_KEY = '-'.join([AGENT_KEY, 'set'])
    ALL_AGENTS_KEY = '-'.join([PREFIX, manager_common.AGENT, 'id', 'all'])

    def __init__(self, client, session):
        self.locker = '%d.%d' % (uuidutils.Gkey.sid, uuidutils.Gkey.pid)
        self.client = client
        self.session = session
        self.alloctime = int(CONF[manager_group.name].glock_alloctime*1000)

    def garbage_key_collection(self, key):
        overtime = self.alloctime + int(time.time()*1000)
        client = self.client
        while True:
            try:
                client.delete(key)
                break
            except (ConnectionError, TimeoutError) as e:
                if int(time.time())*1000 > overtime:
                    LOG.critical('DELETE key %s fail %s' % (key, e.__class__.__name__))
                    client.add_garbage_keys(key, self.locker)
                    break
            eventlet.sleep(0)

    def garbage_member_collection(self, key, members):
        overtime = self.alloctime + int(time.time()*1000)
        client = self.client
        while True:
            try:
                count = client.srem(key, *members)
                if count != len(members):
                    LOG.critical('SREM %s from %s, just success %d' % (str(members), key, count))
                break
            except (ConnectionError, TimeoutError) as e:
                if int(time.time())*1000 > overtime:
                    LOG.critical('SREM %s from %s fail %s' % (str(members), key, e.__class__.__name__))
                    break
            except ResponseError:
                break
            eventlet.sleep(0)

    def lock(self, target):
        method = '_lock_%s' % target
        if not hasattr(self, method):
            raise NotImplementedError('lock %s not exist' % method)
        return getattr(self, method)

    @contextlib.contextmanager
    def _lock_autorelase(self, key, expire):
        overtime = self.alloctime + int(time.time()*1000)
        client = self.client
        while True:
            if client.set(key, self.locker, nx=True):
                break
            if int(time.time()*1000) > overtime:
                raise exceptions.AllocLockTimeout('Alloc key %s timeout' % key)
            eventlet.sleep(0.003)
        try:
            yield
        except Exception:
            client.delete(key)
        else:
            client.expire(key, expire)

    @contextlib.contextmanager
    def _lock_all_agents(self):
        overtime = self.alloctime + int(time.time()*1000)
        client = self.client
        while True:
            if client.set(self.AGENT_KEY, self.locker, nx=True):
                break
            if int(time.time()*1000) > overtime:
                raise exceptions.AllocLockTimeout('Alloc key %s timeout' % self.AGENT_KEY)
            eventlet.sleep(0.003)
        try:
            yield manager_common.ALL_AGENTS
        finally:
            self.garbage_key_collection(self.AGENT_KEY)

    @contextlib.contextmanager
    def _lock_agents(self, agents):
        count = len(agents)
        overtime = self.alloctime + int(time.time()*1000)
        client = self.client
        session = self.session(readonly=True)
        query = model_query(session, Agent,
                            filter=and_(Agent.agent_id.in_(agents),
                                        Agent.status > manager_common.DELETED))
        agents_ids = []
        while True:
            wpipe = None
            try:
                agents = query.all()
                if count != len(agents):
                    raise exceptions.TargetCountUnequal('Target agents count %d, but found %d in database' %
                                                        (count, len(agents)))
                agents_ids = argutils.map_with([agent.agent_id for agent in agents], str)
                while True:
                    try:
                        locked = client.sinter(self.AGENT_KEY, *agents_ids)
                    except ResponseError as e:
                        if not e.message.startswith('WRONGTYPE'):
                            raise
                        locked = True
                    if not locked:
                        break
                    if int(time.time()*1000) <= overtime:
                        eventlet.sleep(0.01)
                    else:
                        raise exceptions.AllocLockTimeout('Lock agents timeout')
                wpipe = client.pipeline()
                wpipe.watch(self.AGENT_KEY)
                wpipe.multi()
                wpipe.sadd(self.AGENT_KEY, *agents_ids)
                wpipe.execute()
                break
            except WatchError:
                if int(time.time()*1000) > overtime:
                    raise exceptions.AllocLockTimeout('Lock agents timeout')
            finally:
                if wpipe:
                    wpipe.reset()
        try:
            yield agents
        finally:
            if agents_ids:
                self.garbage_member_collection(self.AGENT_KEY, agents_ids)

    @contextlib.contextmanager
    def _lock_entitys(self, endpoint, entitys):
        count = len(entitys)
        overtime = self.alloctime + int(time.time()*1000)
        client = self.client
        session = self.session(readonly=True)
        query = model_query(session, AgentEntity,
                            filter=and_(AgentEntity.entity.in_(entitys),
                                        AgentEntity.endpoint == endpoint))
        endpoint_key = '%s-%s' % (self.PREFIX, endpoint)
        agents_ids = set()
        entitys_ids = set()
        while True:
            wpipe = None
            try:
                entitys = query.all()
                if count != len(entitys):
                    raise exceptions.TargetCountUnequal('Target entitys %d, but just found %d in database' %
                                                        (count, len(entitys)))
                for entity in entitys:
                    entitys_ids.add(entity.entity)
                    agents_ids.add(entity.agent_id)
                agents_ids = map(str, agents_ids)
                entitys_ids = map(str, entitys_ids)
                while int(time.time()*1000) <= overtime:
                    with client.pipeline() as pipe:
                        pipe.multi()
                        pipe.sinter(self.AGENT_KEY, agents_ids)
                        pipe.sinter(endpoint_key, entitys_ids)
                        results = pipe.execute()
                    if all([True if len(result) == 0 else False for result in results]):
                        break
                    else:
                        eventlet.sleep(0.01)
                wpipe = client.pipeline()
                wpipe.watch(self.AGENT_KEY, endpoint_key)
                wpipe.multi()
                wpipe.sadd(self.AGENT_KEY, *agents_ids)
                wpipe.sadd(endpoint_key, *entitys_ids)
                wpipe.execute()
                break
            except WatchError:
                if int(time.time()*1000) > overtime:
                    raise exceptions.AllocLockTimeout('Lock entitys timeout')
            except ResponseError as e:
                if not e.message.startswith('WRONGTYPE'):
                    raise
                if int(time.time()*1000) > overtime:
                    raise exceptions.AllocLockTimeout('Lock entitys timeout')
            finally:
                if wpipe:
                    wpipe.reset()
        try:
            yield entitys
        finally:
            self.garbage_member_collection(self.AGENT_KEY, agents_ids)
            self.garbage_member_collection(endpoint_key, entitys_ids)

    @contextlib.contextmanager
    def _lock_endpoint(self, endpoint):
        overtime = self.alloctime + int(time.time()*1000)
        client = self.client
        endpoint_key = '%s-%s' % (self.PREFIX, endpoint)
        while True:
            if client.set(endpoint_key, self.locker, nx=True):
                break
            if int(time.time()*1000) > overtime:
                raise exceptions.AllocLockTimeout('Alloc key %s timeout' % endpoint_key)
            eventlet.sleep(0)
        try:
            yield
        finally:
            self.garbage_key_collection(endpoint_key)

    @property
    def all_agents(self):
        client = self.client
        key = self.ALL_AGENTS_KEY
        all_ids = client.smembers(key)
        id_set = set()
        if not all_ids:
            # lazy init all agent id cache
            session = self.session(readonly=True)
            # doble check
            with self._lock_all_agents():
                all_ids = client.smembers(key)
                if not all_ids:
                    query = session.query(Agent.agent_id).filter(Agent.status > manager_common.DELETED)
                    for result in query:
                        id_set.add(result[0])
                    if id_set:
                        client.sadd(key, *[str(_id) for _id in id_set])
                    return id_set
        for agent_id in all_ids:
            id_set.add(int(agent_id))
        return id_set

    def flush_all_agents(self):
        with self._lock_all_agents():
            # clean all id key
            self.garbage_key_collection(self.ALL_AGENTS_KEY)

    def add_agent(self, body):
        agent = Agent()
        try:
            agent.host = validators['type:hostname'](body.pop('host'))
            agent.agent_type = body.pop('agent_type', None)
            if agent.agent_type is None or len(agent.agent_type) > 64:
                raise ValueError('Agent type info over size')
            if body.get('ports_range', None) is not None:
                agent.ports_range = jsonutils.dumps(body.pop('ports_range'))
            agent.memory = int(body.pop('memory'))
            agent.cpu = int(body.pop('cpu'))
            agent.disk = int(body.pop('disk'))
            endpoints = validateutils.validate_endpoints(body.pop('endpoints', []))
        except KeyError as e:
            raise InvalidArgument('Can not find argument: %s' % e.message)
        except ValueError as e:
            raise InvalidArgument('Argument value type error: %s' % e.message)
        agent.create_time = timeutils.realnow()
        session = self.session()
        with self._lock_all_agents():
            host_filter = and_(Agent.host == agent.host, Agent.status > manager_common.DELETED)
            if model_count_with_key(session, Agent.host, filter=host_filter) > 0:
                raise exceptions.AgentHostExist('Agent with host %s alreday eixst' % agent.host)
            agent_id = model_autoincrement_id(session, Agent.agent_id)
            with session.begin():
                agent.agent_id = agent_id
                if agent.endpoints:
                    for endpoint in agent.endpoints:
                        endpoint.agent_id = agent_id
                session.add(agent)
                session.flush()
                if endpoints:
                    for endpoint in endpoints:
                        session.add(AgentEndpoint(agent_id=agent_id, endpoint=endpoint))
                        session.flush()
                # add new agent_id to cache all agent_id
                if not self.client.sadd(self.ALL_AGENTS_KEY, str(agent.agent_id)):
                    raise exceptions.CacheStoneError('Cant not add agent_id to redis, key %s' % self.ALL_AGENTS_KEY)
        return agent

    @contextlib.contextmanager
    def delete_agent(self, agent):
        with self._lock_agents([agent.agent_id if isinstance(agent, Agent) else agent, ]) as agents:
            agent = agents[0]
            if len(agent.entitys) > 0:
                raise InvalidArgument('Can not delete agent, entity not 0')
            session = self.session()
            query = model_query(session, Agent,
                                filter=and_(Agent.agent_id == agent.agent_id,
                                            Agent.status > manager_common.DELETED))
            with session.begin():
                # Mark agent deleted
                query.update({'status': manager_common.DELETED})
                # Delete endpoint of agent
                yield agent
            self.garbage_member_collection(self.ALL_AGENTS_KEY, [str(agent.agent_id), ])
