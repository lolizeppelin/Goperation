import time
import os
import functools

from simpleutil.log import log as logging
from simpleutil.utils import systemutils

from sqlalchemy.pool import NullPool
from simpleservice.ormdb.argformater import connformater
from simpleservice.ormdb.engines import create_engine
from simpleservice.ormdb.tools.utils import re_create_schema
from simpleservice.ormdb.tools.backup import mysqldump
from simpleservice.ormdb.tools.backup import mysqlload

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
                 revertable=False,
                 rollback=False):
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
        if not (self.localfile.path.endswith('.sql') or self.localfile.path.endswith('.gz')):
            middleware.filemanager.delete(self.source)
            raise ValueError('Database file not endwith sql or gz')
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
        return self.localfile.path


class DbBackUpFile(TaskPublicFile):

    def __init__(self, destination):
        if os.path.exists(destination):
            raise ValueError('Database backup file %s alreday exist')
        if not (destination.endswith('.sql') or destination.endswith('.gz')):
            raise ValueError('Database backup file name not endwith sql or gz')
        self.destination = os.path.abspath(destination)

    def prepare(self, middleware=None, timeout=None):
        path = os.path.split(self.destination)[0]
        if not os.path.exists(path):
            raise ValueError('Database backup dir not exist')
        else:
            if not os.path.isdir(path):
                raise ValueError('Database backup dir %s is not dir' % path)

    def clean(self):
        if os.path.exists(self.destination):
            os.remove(self.destination)

    def _file(self):
        return self.destination


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
            if database.update:
                if not isinstance(database.update, TaskPublicFile):
                    raise TypeError('DbUpdateSqlGet need database.update TaskPublicFile')
                LOG.info('Prepare database update source %s' % database.update.source)
                database.update.prepare(self.middleware, timeout)

    def revert(self, result, *args, **kwargs):
        super(DbUpdateSqlGet, self).revert(result, *args, **kwargs)
        if isinstance(result, failure.Failure):
            for database in self.databases:
                if database.update:
                    database.update.clean()


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


class MysqlDump(StandardTask):

    @property
    def taskname(self):
        return self.__class__.__name__ + '-' + self.database.schema

    def __init__(self, middleware, database):
        """backup app database"""
        self.database = database
        super(MysqlDump, self).__init__(middleware)

    def execute(self, table=True, proc=True):
        database = self.database
        if not isinstance(database.backup, TaskPublicFile):
            raise TypeError('MysqlDump need database.backup TaskPublicFile')
        database.backup.prepare(middleware=self.middleware)
        timeout = database.timeout or 3600
        if not database.schema or database.schema.lower() == 'mysql':
            raise RuntimeError('Schema value error')
        func = None
        if systemutils.LINUX:
            func = functools.partial(utils.safe_fork,
                                     user=self.middleware.entity_user,
                                     group=self.middleware.entity_group)
        extargs = []
        if not table:
            extargs.append('-t')
        if proc:
            extargs.append('-R')
        mysqldump(dumpfile=database.backup.file,
                  host=database.host, port=database.port,
                  user=database.user, passwd=database.passwd,
                  schema=database.schema,
                  character_set=database.character_set,
                  callable=func,
                  timeout=timeout)

    def revert(self, result, *args, **kwargs):
        super(MysqlDump, self).revert(result, *args, **kwargs)
        if isinstance(result, failure.Failure):
            database = self.database
            database.backup.clean()
            self.middleware.set_return(self.taskname, common.REVERTED)
            # if os.path.exists(database.backup.file):
            #     os.remove(database.backup.file)


class MysqlUpdate(StandardTask):
    @property
    def taskname(self):
        return self.__class__.__name__ + '-' + self.database.schema

    def __init__(self, middleware, database):
        self.database = database
        self.executed = 0
        super(MysqlUpdate, self).__init__(middleware)

    def execute_sql_from_file(self, sql_file, logfile=None, timeout=None):
        database = self.database
        func = None
        if systemutils.LINUX:
            func = functools.partial(utils.safe_fork,
                                     user=self.middleware.entity_user,
                                     group=self.middleware.entity_group)
        self.executed = 1
        mysqlload(loadfile=sql_file,
                  host=database.host, port=database.port,
                  user=database.user, passwd=database.passwd,
                  schema=database.schema,
                  character_set=database.character_set,
                  extargs=None,
                  logfile=logfile,
                  callable=func,
                  timeout=timeout)

    def execute_sql_from_row(self, logfile=None, timeout=None):
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
                    msg = 'execute sql fail, index %d, sql file %s' % (self.executed + 1,
                                                                       database.update.file)
                    with open(logfile, 'w') as f:
                        f.write(msg + '\n')
                        f.write(sql + '\n')
                        f.write(str(e))
                    self.middleware.dberrors.append(sql)
                    LOG.error(msg)
                    # engine.close()
                    raise exceptions.DatabaseExecuteError(msg)

    def execute(self):
        if self.middleware.is_success(self.taskname):
            return
        database = self.database
        timeout = database.timeout or 3600
        if not database.schema or database.schema.lower() in NOTALLOWD_SCHEMAS:
            raise RuntimeError('Schema is mysql, not allowed')
        localfile = database.update.localfile
        logfile = os.path.join(self.middleware.logpath, '%s.%s.%s.log' % (self.__class__.__name__.lower(),
                                                                          database.schema, localfile.md5))
        # update by formated sql
        if database.update.sql:
            LOG.debug('Execute database update from row')
            self.execute_sql_from_row(logfile, timeout)
        # update by execute sql file
        else:
            LOG.debug('Execute database update from file')
            self.execute_sql_from_file(database.update.file, logfile, timeout)
        # remove logfile if not error
        try:
            if os.path.exists(logfile):
                os.remove(logfile)
        except (OSError, IOError):
            LOG.error('Remove log file %s fail' % logfile)

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
                    engine = create_engine(connformater % {'user': database.user,
                                                           'passwd': database.passwd,
                                                           'host': database.host,
                                                           'port': database.port,
                                                           'schema': database.schema},
                                           thread_checkin=False,
                                           poolclass=NullPool,
                                           charset=database.character_set)
                    LOG.warning('Database %s will drop and re create in %s:%d' % (database.schema,
                                                                                  database.host,
                                                                                  database.port))
                    re_create_schema(engine)
                    self.execute_sql_from_file(database.backup.file)
                    self.executed = 0
                    LOG.info('Revert database success')
                self.middleware.set_return(self.taskname, common.REVERTED)
            else:
                if isinstance(result, failure.Failure):
                    LOG.error('Database update fail, not revert because not backup file or unable to revert')


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
        lfow = lf.Flow(name='db_%s_%d_%d' % (endpoint_name, entity, index),
                       retry=retry)
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
