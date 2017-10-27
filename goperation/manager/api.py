import time
import eventlet
import contextlib
import six

from sqlalchemy.sql import and_

from redis.exceptions import ConnectionError
from redis.exceptions import TimeoutError
from redis.exceptions import WatchError

from simpleutil.config import cfg
from simpleutil.utils import timeutils
from simpleutil.utils import uuidutils
from simpleutil.log import log as logging
from simpleutil.common.exceptions import InvalidArgument

from simpleservice.plugin.models import GkeyMap
from simpleservice.ormdb.api import model_query
from simpleservice.ormdb.api import model_count_with_key
from simpleservice.ormdb.api import model_autoincrement_id
from simpleservice.ormdb.api import MysqlDriver
from simpleservice.plugin.rpcclient import RPCClientBase
from simpleservice.rpc.config import rpc_client_opts

from goperation import lock
from goperation.redis import GRedisPool
from goperation.manager import exceptions
from goperation.manager import common as manager_common
from goperation.manager.config import manager_group
from goperation.manager.config import manager_rabbit_group
from goperation.manager.models import Agent
from goperation.manager.models import AgentEndpoint
from goperation.manager.models import AgentEntity


LOG = logging.getLogger(__name__)

CONF = cfg.CONF

DbDriver = None
GRedis = None
SERVER_ID = None
RPCClient = None
GlobalDataClient = None


def init_mysql_session():
    global DbDriver
    if DbDriver is None:
        with lock.get('mysql'):
            if DbDriver is None:
                LOG.info("Try connect database for manager")
                mysql_driver = MysqlDriver(manager_group.name,
                                           CONF[manager_group.name])
                mysql_driver.start()
                DbDriver = mysql_driver
    else:
        LOG.warning("Do not call init_mysql_session more then once")


def get_session(readonly=False):
    if DbDriver is None:
        init_mysql_session()
    if readonly:
        return DbDriver.rsession
    return DbDriver.session


def init_server_id():
    global SERVER_ID
    if SERVER_ID is None:
        with lock.get('sid'):
            if SERVER_ID is None:
                session = get_session()
                with session.begin():
                    query = model_query(session, GkeyMap, filter={'host': CONF.host})
                    result = query.one_or_none()
                    if not result:
                        upquery = model_query(session, GkeyMap)
                        upquery.update(dict(host=CONF.host),
                                       update_args={'mysql_limit': 1})
                        result = query.first()
                    SERVER_ID = result.sid
    else:
        LOG.warning("Do not call init_server_id more then once")


def init_redis():
    global GRedis
    if GRedis is not None:
        LOG.warning("Do not call init_redis more then once")
        return
    with lock.get('redis'):
        if GRedis is None:
            if SERVER_ID is None:
                init_server_id()
            conf = CONF[manager_group.name]
            kwargs = dict(server_id=SERVER_ID,
                          max_connections=conf.redis_pool_size,
                          host=conf.redis_host,
                          port=conf.redis_port,
                          db=conf.redis_db,
                          password=conf.redis_password,
                          socket_connect_timeout=conf.redis_connect_timeout,
                          socket_timeout=conf.redis_socket_timeout,
                          heart_beat_over_time=conf.redis_heartbeat_overtime,
                          heart_beat_over_time_max_count=conf.redis_heartbeat_overtime_max_count,
                          )
            redis_client = GRedisPool.from_url(**kwargs)
            redis_client.start()
            GRedis = redis_client


def get_redis():
    if GRedis is None:
        init_redis()
    return GRedis


get_cache = get_redis


def init_rpc_client():
    global RPCClient
    if RPCClient is None:
        with lock.get('rpc'):
            if RPCClient is None:
                LOG.info("Try init rpc client for manager")
                RPCClient = ManagerRpcClient()
    else:
        LOG.warning("Do not call init_rpc_client more then once")


def get_client():
    if RPCClient is None:
        init_rpc_client()
    return RPCClient


def rpcfinishtime(starttime=None):
    rpc_conf = CONF[manager_rabbit_group.name]
    if not starttime:
        starttime = int(timeutils.realnow())
    offset_time = rpc_conf.rpc_send_timeout * (rpc_conf.rpc_send_retry + 1)
    return starttime + offset_time + 4


def init_global_data_client():
    global GlobalDataClient
    if GlobalDataClient is None:
        with lock.get('sync'):
            if GlobalDataClient is None:
                LOG.info("Try init glock client for manager")
                GlobalDataClient = GlobalData(client=get_redis(),
                                              rsession=get_session(readonly=True),
                                              wsession=get_session(readonly=False))
    else:
        LOG.warning("Do not call init_sync_client more then once")


def get_global():
    if GlobalDataClient is None:
        init_global_data_client()
    return GlobalDataClient


class ManagerRpcClient(RPCClientBase):
    """singleton Rpc client"""
    def __init__(self):
        CONF.register_opts(rpc_client_opts, manager_rabbit_group)
        super(ManagerRpcClient, self).__init__(CONF[manager_rabbit_group.name])
        self.rpcdriver.init_timeout_record(session=get_session(readonly=False))


class GlobalData(object):

    PREFIX = CONF[manager_group.name].redis_key_prefix
    AGENT_KEY = '-'.join([PREFIX, manager_common.AGENT])
    AGENTS_KEY = '-'.join([AGENT_KEY, 'set'])
    ALL_AGENTS_KEY = '-'.join([PREFIX, manager_common.AGENT, 'id', 'all'])

    def __init__(self, client, rsession, wsession):
        self.locker = '.'.join([uuidutils.Gkey.sid, uuidutils.Gkey.pid])
        self.client = client
        self.rsession = rsession
        self.wsession = wsession
        self.alloctime = int(CONF[manager_group.name].redis_alloctime*1000)

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
            eventlet.sleep(0)

    def lock(self, target):
        return getattr(self, '_lock_%s' % target)

    @contextlib.contextmanager
    def _lock_all_agents(self):
        overtime = self.alloctime + int(time.time()*1000)
        client = self.client
        while True:
            if client.set(self.AGENT_KEY, self.locker, nx=True):
                break
            if int(time.time()*1000) > overtime:
                raise exceptions.AllocLockTimeout('Alloc key %s timeout' % self.AGENTS_KEY)
            eventlet.sleep(0)
        try:
            yield manager_common.ALL_AGENTS
        finally:
            self.garbage_key_collection(self.AGENT_KEY)

    @contextlib.contextmanager
    def _lock_agents(self, agents):
        count = len(agents)
        overtime = self.alloctime + int(time.time()*1000)
        client = self.client
        session = self.rsession
        query = model_query(session, Agent,
                            filter=and_(Agent.agent_id.in_(agents), Agent.status > manager_common.DELETED))
        agents_ids = []
        while True:
            try:
                with self._lock_all_agents():
                    agents = query.all()
                    if count != len(agents):
                        raise exceptions.TargetCountUnequal('Target agents count %d, but found %d in database' %
                                                            (count, len(agents)))
                    agents_ids = map(str, [agent.agent_id for agent in agents])
                    while client.sinter(self.AGENTS_KEY, agents_ids) and int(time.time()*1000) <= overtime:
                        eventlet.sleep(0)
                    wpipe = client.pipeline()
                    wpipe.watch(self.AGENTS_KEY)
                wpipe.multi()
                wpipe.sadd(self.AGENTS_KEY, *agents_ids)
                wpipe.execute()
            except WatchError:
                wpipe.reset()
                if int(time.time()*1000) > overtime:
                    raise exceptions.AllocLockTimeout('Lock agents timeout')
        try:
            yield agents
        finally:
            if agents_ids:
                self.garbage_member_collection(self.AGENTS_KEY, agents_ids)

    @contextlib.contextmanager
    def _lock_entitys(self, endpoint, entitys):
        count = len(entitys)
        overtime = self.alloctime + int(time.time()*1000)
        client = self.client
        session = self.rsession
        query = model_query(session, AgentEntity,
                            filter=and_(AgentEntity.entity.in_(entitys),
                                        AgentEntity.endpoint == endpoint))
        entitys_key = '-'.join([self.PREFIX, endpoint, manager_common.ENTITY, 'set'])
        agents_ids = set()
        entitys_ids = set()
        while True:
            try:
                with self._lock_all_agents():
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
                            pipe.sinter(self.AGENTS_KEY, agents_ids)
                            pipe.sinter(entitys_key, entitys_ids)
                            retsults = pipe.execute()
                        if all([True if len(result) == 0 else False for result in retsults]):
                            break
                        else:
                            eventlet.sleep(0)
                    wpipe = client.pipeline()
                    wpipe.watch(self.AGENTS_KEY, entitys_key)
                with client.pipeline() as pipe:
                    pipe.multi()
                    pipe.sinter(self.AGENTS_KEY, agents_ids)
                    pipe.sinter(entitys_key, entitys_ids)
                    retsults = pipe.execute()
                if all([True if len(result) == 0 else False for result in retsults]):
                    wpipe.multi()
                    wpipe.sadd(entitys_key, *agents_ids)
                    wpipe.sadd(entitys_key, *entitys_ids)
                    wpipe.execute()
                    break
            except WatchError:
                wpipe.reset()
                if int(time.time()*1000) > overtime:
                    raise exceptions.AllocLockTimeout('Lock entitys timeout')
        try:
            yield entitys
        finally:
            self.garbage_member_collection(self.AGENTS_KEY, agents_ids)
            self.garbage_member_collection(entitys_key, entitys_ids)


    @contextlib.contextmanager
    def _lock_all_endpoint(self, endpoint):
        overtime = self.alloctime + int(time.time()*1000)
        client = self.client
        endpoint_key = '-'.join([self.PREFIX, endpoint,'all'])
        while True:
            if client.set(endpoint_key, self.locker, nx=True):
                break
            if int(time.time()*1000) > overtime:
                raise exceptions.AllocLockTimeout('Alloc key %s timeout' % self.AGENTS_KEY)
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
            session = self.rsession
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
        with self._lock_all_agents:
            # clean all id key
            self.garbage_key_collection(self.ALL_AGENTS_KEY)

    def add_agent(self, agent):
        with self._lock_agents([agent.agent_id, ]):
            host_filter = and_(Agent.host == agent.host, Agent.status > manager_common.DELETED)
            if model_count_with_key(self.rsession, Agent.host, filter=host_filter) > 0:
                raise exceptions.AgentHostExist('Agent with host %s alreday eixst' % agent.host)
            with self.wsession.begin(subtransactions=True):
                new_agent_id = model_autoincrement_id(self.wsession, Agent.agent_id)
                agent.agent_id = new_agent_id
                self.wsession.add(agent)
                self.wsession.flush()
                # add new agent_id to cache all agent_id
                if not self.client.sadd(self.ALL_AGENTS_KEY, str(agent.agent_id)):
                    raise exceptions.CacheStoneError('Cant not add agent_id to redis, key %s' % self.ALL_AGENTS_KEY)

    @contextlib.contextmanager
    def delete_agent(self, agent):
        with self._lock_agents([agent.agent_id if isinstance(agent, Agent) else agent, ]) as agents:
            agent = agents[0]
            if len(agent.entitys) > 0:
                raise InvalidArgument('Can not delete agent, entity not 0')
            query = model_query(self.wsession, Agent,
                                filter=and_(Agent.agent_id == agent.agent_id,
                                            Agent.status > manager_common.DELETED))
            with self.wsession.begin(subtransactions=True):
                # Mark agent deleted
                query.update({'status': manager_common.DELETED})
                # Delete endpoint of agent
                yield agent
            self.garbage_member_collection(self.ALL_AGENTS_KEY, [str(agent.agent_id), ])
