import time
import os
import sys
import subprocess

from simpleutil.log import log as logging
from simpleutil.utils import systemutils

from sqlalchemy.pool import NullPool
from simpleservice.ormdb.argformater import connformater
from simpleservice.ormdb.engines import create_engine
from simpleservice.ormdb.tools.utils import re_create_schema

from simpleflow.types import failure
from simpleflow.retry import Times
from simpleflow.patterns import linear_flow as lf
from simpleflow.patterns import unordered_flow as uf

from goperation import utils
from goperation.filemanager import TargetFile
from goperation.taskflow import common
from goperation.taskflow import exceptions
from goperation.manager.rpc.agent.application.taskflow.base import StandardTask
from goperation.manager.rpc.agent.application.taskflow.base import format_store_rebind


LOG = logging.getLogger(__name__)

NOTALLOWD_SCHEMAS = frozenset(['mysql', 'information_schema', 'performance_schema'])


class DbUpdateFile(TargetFile):

    def __init__(self, source, rollback=False, formater=None):
        super(DbUpdateFile, self).__init__(source)
        # update will rollback when task pipe fail
        self.rollback = rollback
        self._formater = formater
        self.sql = []

    def clean(self):
        super(DbUpdateFile, self).clean()
        del self.sql[:]

    def format(self):
        if self._formater:
            self.sql = self._formater(self.realpath)


class Database(object):

    def __init__(self,
                 backup, update,
                 **kwargs):
        """
        backup  path info
        update  class of DbUpdateFile
        """
        self.backup = backup
        self.update = update
        self.user = kwargs['user']
        self.passwd = kwargs['passwd']
        self.host = kwargs['host']
        self.port = kwargs['port']
        self.schema = kwargs['schema']
        self.character_set = kwargs.get('character_set', 'utf8')
        self.collation_type = kwargs.get('collation_type', None)
        self.timeout = kwargs.get('timeout', None)
        self.retry = 0


class DbUpdateSqlGet(StandardTask):
    """Download  database  upload file"""

    @property
    def taskname(self):
        return self.__class__.__name__ + '-' + str(self.middleware.entity)

    def __init__(self, middleware, databases, rebind=None):
        super(DbUpdateSqlGet, self).__init__(middleware, rebind=rebind)
        self.databases = databases

    def execute(self, timeout):
        for database in self.databases:
            if database.update:
                if database.update.realpath is None:
                    self.middleware.filemanager.get(database.update, download=True, timeout=timeout)
                    database.update.format()

    def revert(self, result, *args, **kwargs):
        super(DbUpdateSqlGet, self).revert(result, *args, **kwargs)
        if isinstance(result, failure.Failure):
            for database in self.databases:
                if database.update:
                    database.update.clean()


class MysqlDump(StandardTask):

    @property
    def taskname(self):
        return self.__class__.__name__ + '-' + self.database.schema

    def __init__(self, middleware, database, rebind=None):
        """backup app database"""
        self.database = database
        super(MysqlDump, self).__init__(middleware, rebind=rebind)

    def execute(self, timeout):
        database = self.database
        if not database.schema or database.schema.lower() == 'mysql':
            raise RuntimeError('Schema value error')
        mysqldump = systemutils.find_executable('mysqldump')
        args = [mysqldump,
                '--default-character-set=%s' % (database.character_set or 'utf8'),
                '-u%s' % database.user, '-p%s' % database.passwd,
                '-h%s' % database.host, '-P%d' % database.port,
                database.schema]
        LOG.debug(' '.join(args))
        with open(os.devnull, 'wb') as nul:
            with open(database.backup, 'wb') as f:
                if systemutils.LINUX:
                    pid = utils.safe_fork(user=self.middleware.entity_user,
                                          group=self.middleware.entity_group)
                    if pid == 0:
                        os.dup2(f.fileno(), sys.stdout.fileno())
                        os.dup2(nul.fileno(), sys.stderr.fileno())
                        os.execv(mysqldump, args)
                    else:
                        utils.wait(pid, timeout)
                else:
                    sub = subprocess.Popen(executable=mysqldump, args=args, stdout=f.fileno(), stderr=nul.fileno())
                    utils.wait(sub, timeout)

    def revert(self, result, *args, **kwargs):
        super(MysqlDump, self).revert(result, *args, **kwargs)
        if isinstance(result, failure.Failure):
            database = self.database
            if os.path.exists(database.backup):
                os.remove(database.backup)


class MysqlUpdate(StandardTask):

    def __init__(self, middleware, database, rebind=None):
        super(MysqlUpdate, self).__init__(middleware, rebind=rebind)
        self.database = database
        self.executed = 0

    def execute_sql_from_file(self, sql_file, timeout=None):
        database = self.database
        mysql = systemutils.find_executable('mysql')
        args = [mysql,
                '--default-character-set=%s' % (database.character_set or 'utf8'),
                '-u%s' % database.user, '-p%s' % database.passwd,
                '-h%s' % database.host, '-P%d' % database.port,
                database.schema]
        LOG.info('Endpoint %s, entity %d call MysqlUpdate for %s' % (self.middleware.endpoint,
                                                                     self.middleware.entity,
                                                                     database.schema))
        with open(os.devnull, 'wb') as nul:
            with open(sql_file, 'rb') as f:
                self.executed = 1
                if systemutils.LINUX:
                    pid = utils.safe_fork(user=self.middleware.entity_user,
                                          group=self.middleware.entity_group)
                    if pid == 0:
                        os.dup2(f.fileno(), sys.stdin.fileno())
                        os.dup2(nul.fileno(), sys.stderr.fileno())
                        os.execv(mysql, args)
                    else:
                        utils.wait(pid, timeout=timeout)
                else:
                    sub = subprocess.Popen(executable=mysql, args=args, stdin=f.fileno(), stderr=nul.fileno())
                    utils.wait(sub, timeout=timeout)

    def execute(self):
        if self.middleware.is_success(self.__class__.__name__):
            return
        database = self.database
        timeout = database.timeout or 3600
        if not database.schema or database.schema.lower() in NOTALLOWD_SCHEMAS:
            raise RuntimeError('Schema is mysql, not allowed')
        # update by formated sql
        if database.update.sql:
            db_info = {'user': database.user,
                       'passwd': database.passwd,
                       'host': database.host,
                       'port': database.port,
                       'schema': database.schema,
                       }
            database_connection = connformater % db_info
            engine = create_engine(database_connection, thread_checkin=False,
                                   poolclass=NullPool,
                                   charset=database.character_set)
            overtime = time.time() + timeout
            with engine.connect() as conn:
                LOG.info('MysqlUpdate connect %s:%d/%s mysql success' %
                         (database.host, database.port, database.schema))
                for sql in database.update.sql:
                    try:
                        if time.time() > overtime:
                            raise exceptions.DatabaseExecuteError('Execute overtime')
                        r = conn.execute(sql)
                        # count = r.rowcount
                        r.close()
                        self.executed += 1
                    except Exception as e:
                        LOG.debug('%s : [%s]' % (e.__class__.__name__, sql))
                        msg = 'execute sql fail, index %d' % (self.executed+1)
                        self.middleware.dberrors.append(sql)
                        LOG.error(msg)
                        # engine.close()
                        raise exceptions.DatabaseExecuteError(msg)
            # engine.close()
        # update by execute sql file
        else:
            self.execute_sql_from_file(database.update.realpath, timeout)

    def revert(self, result, *args, **kwargs):
        super(MysqlUpdate, self).revert(result, *args, **kwargs)
        database = self.database
        if isinstance(result, failure.Failure) or database.update.rollback:
            # revert need backup
            if database.backup:
                LOG.info('Try revert %s %d database %s:%d/%s ' % (self.middleware.endpoint,
                                                                  self.middleware.entity,
                                                                  database.host,
                                                                  database.port,
                                                                  database.schema))
                if not self.executed:
                    LOG.info('Database %s:%d/%s no sql executed, '
                             'nothing will be reverted' % (database.host,
                                                           database.port,
                                                           database.schema))
                else:
                    if not os.path.exists(database.backup):
                        msg = 'No backup database file found! can not revert'
                        LOG.error(msg)
                        raise exceptions.DatabaseRevertError(msg)

                    db_info = {'user': database.user,
                               'passwd': database.passwd,
                               'host': database.host,
                               'port': database.port,
                               'schema': database.schema,
                               }
                    database_connection = connformater % db_info
                    engine = create_engine(database_connection, thread_checkin=False,
                                           poolclass=NullPool,
                                           charset=database.character_set)
                    LOG.warning('Database %s will drop and re create in %s:%d' % (database.schema,
                                                                                  database.host,
                                                                                  database.port))
                    re_create_schema(engine)
                    self.execute_sql_from_file(database.backup)
                    self.executed = 0
                    LOG.info('Revert database success')
                self.middleware.set_return(self.taskname, common.REVERTED)
            else:
                if isinstance(result, failure.Failure):
                    LOG.error('Update fail, but not backup file found')
                    raise ValueError('Can not rollback, no backup file found')


def mysql_flow_factory(app, store):
    if not app.databases:
        return None
    middleware = app.middleware
    endpoint_name = middleware.endpoint.namespace
    entity = middleware.entity
    uflow = uf.Flow('dmp_and_up_%s_%d' % (endpoint_name, entity))
    for index, database in enumerate(app.databases):
        retry = None
        if database.retry:
            retry = Times(attempts=database.retry,
                          name='db_retry_%s_%d_%d' % (endpoint_name, entity, index))
        lfow = lf.Flow(name='db_%s_%d_%d' % (endpoint_name, entity, index), retry=retry)
        if database.backup:
            rebind = ['db_dump_timeout']
            format_store_rebind(store, rebind)
            lfow.add(MysqlDump(middleware, database, rebind=rebind))
        if database.update:
            if database.update.rollback and not database.backup:
                raise ValueError('Database rollback need backup')
            rebind = ['db_update_timeout']
            format_store_rebind(store, rebind)
            lfow.add(MysqlUpdate(middleware, database, rebind=rebind))
        if len(lfow):
            uflow.add(lfow)
        else:
            del lfow

    def del_flow():
        del uflow
        return None

    return uflow if len(uflow) else del_flow()
