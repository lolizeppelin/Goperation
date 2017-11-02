# -*- coding: UTF-8 -*-
from redis.connection import Connection
from redis.connection import ConnectionPool
from redis.exceptions import ConnectionError

from simpleutil.log import log as logging

from simpleutil.utils.lockutils import PriorityLock
from simpleutil.utils.timeutils import monotonic


LOG = logging.getLogger(__name__)


class ConnectionEx(Connection):

    def __init__(self, *args, **kwargs):
        Connection.__init__(self, *args, **kwargs)
        # 上次心跳包时间
        self.last_beat = 0
        # 初始化的时候立刻链接
        self.connect()

    def connect(self):
        if self._sock:
            return
        super(ConnectionEx, self).connect()
        self.last_beat = monotonic()*1000

    def read_response(self):
        result = super(ConnectionEx, self).read_response()
        # 更新心跳时间
        self.last_beat = monotonic()*1000
        return result


class ConnectionPoolEx(ConnectionPool):

    def __init__(self, connection_class=Connection, max_connections=None,
                 **connection_kwargs):
        super(ConnectionPoolEx, self).__init__(connection_class=connection_class,
                                               max_connections=max_connections,
                                               **connection_kwargs)
        self.lock = PriorityLock()

    def make_connection(self):
        if self._created_connections >= self.max_connections:
            raise ConnectionError("Too many connections")
        connection = self.connection_class(**self.connection_kwargs)
        # 链接计数器在实例生成后才增加,绿化后需要
        self._created_connections += 1
        return connection

    def get_connection(self, command_name, *keys, **options):
        self._checkpid()
        if command_name.lower() == 'ping':
            priority = 1
        else:
            priority = 0
        with self.lock.priority(priority):
            try:
                # 重写这里,从左边pop,避免heartbeat检查同一个链接
                connection = self._available_connections.pop(0)
            except IndexError:
                connection = self.make_connection()
            self._in_use_connections.add(connection)
            return connection

    def kickout(self, connection):
        self._checkpid()
        if connection.pid != self.pid:
            return
        self._in_use_connections.remove(connection)
        self._created_connections -= 1
