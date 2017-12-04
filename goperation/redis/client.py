# -*- coding: UTF-8 -*-
import six
import eventlet
from redis import StrictRedis

# 异常
from redis.exceptions import ConnectionError
from redis.exceptions import TimeoutError
from redis.exceptions import WatchError
from redis.exceptions import RedisError

from simpleutil.log import log as logging
from simpleutil.utils.timeutils import monotonic

from goperation.redis.connection import ConnectionEx
from goperation.redis.connection import ConnectionPoolEx


LOG = logging.getLogger(__name__)

HEART_BEAT_OVER_TIME = 5000
HEART_BEAT_OVER_TIME_MAX_COUNT = 3


class GRedisPool(StrictRedis):

    def __init__(self, *args, **kwargs):
        self.server_id = str(kwargs.pop('server_id'))
        LOG.info('GLockRedis client start with server_id %s' % self.server_id)
        self.heart_beat_over_time = kwargs.pop('heart_beat_over_time')
        self.heart_beat_over_time_max_count = kwargs.pop('heart_beat_over_time_max_count')
        self.reserve_time = kwargs.pop('reserve_time')
        StrictRedis.__init__(self, *args, **kwargs)
        self.running = False
        self.garbage_keys = dict()

    @classmethod
    def from_url(cls, **kwargs):
        max_connections = int(kwargs.pop('max_connections', 4))
        server_id = kwargs.pop('server_id', 0)
        heart_beat_over_time = kwargs.pop('heart_beat_over_time',
                                          HEART_BEAT_OVER_TIME)
        heart_beat_over_time_max_count = kwargs.pop('heart_beat_over_time_max_count',
                                                    HEART_BEAT_OVER_TIME_MAX_COUNT)
        connection_pool = ConnectionPoolEx(connection_class=ConnectionEx,
                                           max_connections=max_connections, **kwargs)
        reserve_time = int(kwargs.get('socket_timeout', 0.5)*1000) + 100
        return cls(connection_pool=connection_pool,
                   # ext argv
                   server_id=server_id,
                   heart_beat_over_time=heart_beat_over_time,
                   heart_beat_over_time_max_count=heart_beat_over_time_max_count,
                   reserve_time=reserve_time)

    def heart_beat_loop(self):
        """
        心跳循环,用于外部domain线程
        PING命令不使用execute_command
        """
        pool = self.connection_pool
        heart_interval = float(self.heart_beat_over_time)*(float(self.heart_beat_over_time_max_count))
        heart_interval_s = heart_interval/1000
        error_connection_count = 0
        while True:
            if not self.running:
                break
            start_time = monotonic()*1000
            connection = None
            try:
                connection = pool.get_connection('PING')
                # 上次链接传包时间大于心跳间隔,发送PING命令
                if start_time - connection.last_beat > heart_interval:
                    connection.send_command("PING")
                    self.parse_response(connection, "PING")
                # 正常释放连接,链接重回可用连接池中
                pool.release(connection)
                if error_connection_count:
                    error_connection_count -= 1
            except (ConnectionError, TimeoutError) as e:
                LOG.warning('Heartbeat loop %(class)s: %(message)s' % {'class': e.__class__.__name__,
                                                                       'message': e.message})
                if connection:
                    # 踢出连接
                    pool.kickout(connection)
                    # 有链接还连续报错
                    # 多等待一段时间
                    if error_connection_count:
                        LOG.error('Heartbeat loop more then once, sleep more time')
                        eventlet.sleep(heart_interval_s*2)
                else:
                    # 分配不到链接,说明全部链接在忙或者无法生成链接(网络故障)
                    eventlet.sleep(heart_interval_s)
                error_connection_count += 1
            # 切换到其他绿色线程
            eventlet.sleep(heart_interval_s)

    def safe_delete(self, key, mark):
        with self.pipeline() as pipe:
            pipe.watch(key)
            _mark = self.get(key)
            if _mark and _mark == mark:
                pipe.multi()
                LOG.info('Safe delete key %s' % key)
                pipe.delete(key)
                pipe.execute(raise_on_error=True)

    def add_garbage_keys(self, key, mark):
        if not self.running:
            try:
                self.safe_delete(key, mark)
            except (ConnectionError, TimeoutError) as e:
                LOG.error('Delete garbage key %s fail,catch %s' % (key, e.__class__.__name__))
        else:
            self.garbage_keys.setdefault(key, mark)

    def garbage_collector_loop(self):
        """
        用于回收删除失败的key
        """
        while True:
            if not self.running:
                break
            if self.garbage_keys:
                key, mark = self.garbage_keys.popitem()
                try:
                    self.safe_delete(key, mark)
                except (ConnectionError, TimeoutError):
                    LOG.warning('Delete garbage key fail, retry')
                    self.garbage_keys.setdefault(key, mark)
                except WatchError:
                    LOG.info('Key %s changed' % key)
                except RedisError:
                    LOG.error('Key %s type error?' % key)
            else:
                eventlet.sleep(0.5)
        # 停止后清理
        while self.garbage_keys:
            key, mark = self.garbage_keys.popitem()
            error_count = 0
            while error_count < 5:
                try:
                    self.safe_delete(key, mark)
                    break
                except (ConnectionError, TimeoutError):
                    error_count += 1
                except WatchError:
                    LOG.info('Key %s changed' % key)
                except RedisError:
                    LOG.error('Key %s type error?' % key)
                    break

        for key in six.iterkeys(self.garbage_keys):
            LOG.error('Garbage keys %s not deleted' % key)

    def start(self, timeout=5.0):
        """
        循环启动
        """
        timeout = float(timeout)
        self.running = True
        # 孵化心跳循环线程
        heartbeat_greenlet = eventlet.spawn_n(self.heart_beat_loop)
        eventlet.sleep(0.1)
        overtime = monotonic() + timeout
        while True:
            if self.connection_pool._created_connections > 0:
                break
            if monotonic() > overtime:
                self.running = False
                heartbeat_greenlet.throw(TimeoutError)
                # 等待前面的绿色线程结束
                eventlet.sleep(1.0)
                raise ConnectionError('redis connection pool empty over %1.2f seconds' % timeout)
            eventlet.sleep(timeout/5.0)
        # 孵化垃圾key删除循环
        eventlet.spawn_n(self.garbage_collector_loop)

    def stop(self):
        self.running = False
