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
from goperation.taskflow import common
from goperation.taskflow import exceptions
from goperation.manager.rpc.agent.application.taskflow.base import StandardTask
from goperation.manager.rpc.agent.application.taskflow.base import TaskPublicFile


LOG = logging.getLogger(__name__)

NOTALLOWD_SCHEMAS = frozenset(['mysql', 'information_schema', 'performance_schema'])


class DbUpdateFile(TaskPublicFile):
    def __init__(self, source,
                 rollback=False,
                 revertable=False):
        if rollback and not revertable:
            raise ValueError('revert is not enable, can not rollback')
        self.source = source
        # update will rollback when task pipe fail
        self.rollback = rollback
        # update can be revert when fail or rollback is true
        self.revertable = revertable
        self.sql = []
        self.localfile = None

    def prepare(self, middleware=None, timeout=None):
        self.localfile = middleware.filemanager.get(self.source, download=True, timeout=timeout)
        try:
            self.format()
        except Exception:
            self.localfile = None
            middleware.filemanager.delete(self.source)
            raise

    def clean(self):
        del self.sql[:]

    def format(self):
        pass

    def _file(self):
        return os.path.abspath(self.localfile.path)


class Database(object):

    def __init__(self,
                 create=None, backup=None, update=None,
                 **kwargs):
        """
        backup  path info
        update  class of DbUpdateFile
        """
        if not backup and update and (update.rollback or update.revertable):
            raise ValueError('No backup, can not rollback or revert')
        self.create = create
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
            if not isinstance(database.update, TaskPublicFile):
                raise TypeError('DbUpdateSqlGet need database.update TaskPublicFile')
            if database.update:
                self.database.update.prepare(self.middleware, timeout)

    def revert(self, result, *args, **kwargs):
        super(DbUpdateSqlGet, self).revert(result, *args, **kwargs)
        if isinstance(result, failure.Failure):
            for database in self.databases:
                if database.update:
                    self.database.update.clean()


class MysqlCreate(StandardTask):
    @property
    def taskname(self):
        return self.__class__.__name__ + '-' + self.database.schema

    def __init__(self, middleware, database):
        """backup app database"""
        self.database = database
        super(MysqlCreate, self).__init__(middleware)

    def execute(self):
        raise NotImplementedError

    def revert(self, result, *args, **kwargs):
        raise NotImplementedError


class MysqlDump(StandardTask):

    @property
    def taskname(self):
        return self.__class__.__name__ + '-' + self.database.schema

    def __init__(self, middleware, database):
        """backup app database"""
        self.database = database
        super(MysqlDump, self).__init__(middleware)

    def execute(self):
        database = self.database
        if not isinstance(database.backup, TaskPublicFile):
            raise TypeError('MysqlDump need database.backup TaskPublicFile')
        timeout = database.timeout or 3600
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
            with open(database.backup.file, 'wb') as f:
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
            if os.path.exists(database.backup.file):
                os.remove(database.backup)
                self.middleware.set_return(self.taskname, common.REVERTED)


class MysqlUpdate(StandardTask):
    @property
    def taskname(self):
        return self.__class__.__name__ + '-' + self.database.schema

    def __init__(self, middleware, database):
        super(MysqlUpdate, self).__init__(middleware)
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

    def execute_sql_from_row(self, timeout=None):
        database = self.database
        db_info = {'user': database.user,
                   'passwd': database.passwd,
                   'host': database.host,
                   'port': database.port,
                   'schema': database.schema}
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
                    msg = 'execute sql fail, index %d, sql file %s' % (self.executed + 1,
                                                                       database.update.file)
                    self.middleware.dberrors.append(sql)
                    LOG.error(msg)
                    # engine.close()
                    raise exceptions.DatabaseExecuteError(msg)

    def execute(self):
        if self.middleware.is_success(self.__class__.__name__):
            return
        database = self.database
        timeout = database.timeout or 3600
        if not database.schema or database.schema.lower() in NOTALLOWD_SCHEMAS:
            raise RuntimeError('Schema is mysql, not allowed')
        # update by formated sql
        if database.update.sql:
            self.execute_sql_from_row(timeout)
        # update by execute sql file
        else:
            self.execute_sql_from_file(database.update.file, timeout)

    def revert(self, result, *args, **kwargs):
        super(MysqlUpdate, self).revert(result, *args, **kwargs)
        database = self.database
        if isinstance(result, failure.Failure) or database.update.rollback:
            # revert need backup
            if database.backup and database.update.revertable:
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
                    self.middleware.set_return(self.taskname, common.REVERTED)
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


def mysql_flow_factory(app, store,
                       create_cls=MysqlCreate,
                       backup_cls=MysqlDump,
                       update_cls=MysqlUpdate):
    if not app.databases:
        return None
    middleware = app.middleware
    endpoint_name = middleware.endpoint
    entity = middleware.entity
    uflow = uf.Flow('db_cbu_%s_%d' % (endpoint_name, entity))
    for index, database in enumerate(app.databases):
        retry = None
        if database.retry:
            retry = Times(attempts=database.retry,
                          name='db_retry_%s_%d_%d' % (endpoint_name, entity, index))
        lfow = lf.Flow(name='db_%s_%d_%d' % (endpoint_name, entity, index), retry=retry)
        if database.create:
            lfow.add(create_cls(middleware, database))
        if database.backup:
            lfow.add(backup_cls(middleware, database))
        if database.update:
            if database.update.rollback and not database.backup:
                raise ValueError('Database rollback need backup')
            lfow.add(update_cls(middleware, database))
        if len(lfow):
            uflow.add(lfow)
        else:
            del lfow

    if len(uflow):
        return uflow

    del uflow
    return None
