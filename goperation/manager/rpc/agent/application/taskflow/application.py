# -*- coding: utf-8 -*-
import os
import functools

from simpleutil.log import log as logging
from simpleutil.utils import systemutils

from simpleutil.utils import zlibutils

from simpleflow.retry import Retry
from simpleflow.retry import REVERT
from simpleflow.retry import RETRY
from simpleflow.types import failure


from goperation.utils import safe_fork
from goperation.taskflow import common
from goperation.manager.rpc.agent.application.taskflow.base import StandardTask
from goperation.manager.rpc.agent.application.taskflow.base import TaskPublicFile

LOG = logging.getLogger(__name__)


class AppUpgradeFile(TaskPublicFile):

    def __init__(self, source,
                 rollback=False,
                 revertable=True):
        if rollback and not revertable:
            raise ValueError('revert is not enable, can not rollback')
        self.source = source
        # update will rollback when task pipe fail
        self.rollback = rollback
        # update can be revert when fail or rollback is true
        self.revertable = revertable
        self.localfile = None

    def prepare(self, middleware=None, timeout=None):
        self.localfile = middleware.filemanager.get(self.source, download=True, timeout=timeout)
        try:
            self.post_check()
        except Exception:
            self.localfile = None
            middleware.filemanager.delete(self.source)
            raise

    def clean(self):
        pass

    def _file(self):
        if not self.localfile:
            raise ValueError('localfile not prepare')
        return os.path.abspath(self.localfile.path)

    def post_check(self):
        pass


class AppRemoteBackupFile(TaskPublicFile):
    def __init__(self, source):
        self.source = source
        self.localfile = None

    def prepare(self, middleware=None, timeout=None):
        LOG.info('AppBackUp get remote backup file')
        self.localfile = middleware.filemanager.get(self.source, download=True, timeout=timeout)
        try:
            self.post_check()
        except Exception:
            middleware.filemanager.delete(self.source)
            self.localfile = None
            raise

    def clean(self):
        pass

    def _file(self):
        if not self.localfile:
            raise ValueError('localfile not prepare')
        return os.path.abspath(self.localfile.path)

    def post_check(self):
        pass


class AppLocalBackupFile(TaskPublicFile):
    def __init__(self, destination, exclude=None, topdir=True,
                 native=True):
        if os.path.exists(destination):
            raise ValueError('backup file %s alreday exist')
        if exclude and not callable(exclude):
            raise TypeError('exclude is not callable')
        self._exclude = exclude
        self.destination = destination
        self.topdir = topdir
        self.native = native

    def prepare(self, middleware=None, timeout=None):
        LOG.info('AppBackUp dump local bakcup file from %s %d' % (middleware.endpoint,
                                                                  middleware.entity))
        src = middleware.apppath
        LOG.debug('AppBackUp dump local bakcup from path %s' % src)
        waiter = zlibutils.async_compress(src, self.destination,
                                          exclude=self.exclude,
                                          native=self.native,
                                          fork=functools.partial(safe_fork,
                                                                 user=middleware.entity_user,
                                                                 group=middleware.entity_group)
                                          if systemutils.LINUX else None, timeout=timeout,
                                          topdir=self.topdir)
        waiter.wait()
        self.post_check()

    @property
    def exclude(self):
        return self._exclude

    def clean(self):
        try:
            os.remove(self.destination)
        except (OSError, IOError):
            LOG.error('Delete file %s fail' % self.destination)

    def _file(self):
        return os.path.abspath(self.destination)

    def post_check(self):
        pass


class AppKill(Retry):

    def __init__(self, name, provides=None, requires=None,
                 auto_extract=True, rebind=None):
        provides = provides if provides else 'kill'
        super(AppKill, self).__init__(name, provides, requires,
                                      auto_extract, rebind)

    def on_failure(self, history, *args, **kwargs):
        if len(history) < 1:
            return RETRY
        return REVERT

    def execute(self, history, *args, **kwargs):
        if len(history) >= 1:
            return True
        return False


class AppUpgradeFileGet(StandardTask):
    """app 程序升级文件获取, 默认提供参数upgradefile"""
    def __init__(self, middleware, upgradefile, rebind=None, provides='upgradefile'):
        super(AppUpgradeFileGet, self).__init__(middleware, rebind=rebind, provides=provides)
        self.upgradefile = upgradefile

    def execute(self, timeout):
        if self.middleware.is_success(self.taskname):
            return self.upgradefile.file
        self.upgradefile.prepare(self.middleware, timeout)
        return self.upgradefile.file

    def revert(self, result, *args, **kwargs):
        super(AppUpgradeFileGet, self).revert(result, *args, **kwargs)
        if isinstance(result, failure.Failure):
            self.middleware.set_return(self.taskname, common.REVERT_FAIL)
            self.upgradefile.clean()
            self.middleware.set_return(self.taskname, common.REVERTED)


class AppBackUp(StandardTask):
    """app 程序文件备份, 默认提供参数backupfile"""
    def __init__(self, middleware, backupfile, rebind=None, provides='backupfile'):
        super(AppBackUp, self).__init__(middleware, rebind=rebind, provides=provides)
        self.backupfile = backupfile

    def execute(self, timeout):
        if self.middleware.is_success(self.taskname):
            return self.backupfile.file

        self.backupfile.prepare(self.middleware, timeout)
        return self.backupfile.file

    def revert(self, result, *args, **kwargs):
        super(AppBackUp, self).revert(result, *args, **kwargs)
        if isinstance(result, failure.Failure):
            self.middleware.set_return(self.taskname, common.REVERT_FAIL)
            self.backupfile.clean()
            self.middleware.set_return(self.taskname, common.REVERTED)


class AppTaskBase(StandardTask):
    """For Application task"""

    def __init__(self, middleware,
                 provides=None,
                 rebind=None, requires=None,
                 revert_rebind=None, revert_requires=None):
        super(AppTaskBase, self).__init__(middleware, provides=provides,
                                          rebind=rebind, requires=requires,
                                          revert_rebind=revert_rebind, revert_requires=revert_requires)


class AppCreateBase(AppTaskBase):
    """创建实体APP
    """


class AppDeleteBase(AppTaskBase):
    """删除实体APP
    """


class AppStartBase(AppTaskBase):
    """程序启动"""


class AppStopBase(AppTaskBase):
    """程序关闭"""


class AppFileUpgradeBase(AppTaskBase):
    """app 程序文件升级"""


class AppFileUpgradeByFile(AppFileUpgradeBase):

    def __init__(self, middleware, exclude=None, native=True,
                 rebind=None, requires='upgradefile',
                 revert_requires='backupfile'):
        if exclude and not callable(exclude):
            raise TypeError('exclude is not callable')
        self._exclude = exclude
        self.native = native
        super(AppFileUpgradeByFile, self).__init__(middleware=middleware,
                                                   rebind=rebind, requires=requires,
                                                   revert_requires=revert_requires)

    def execute(self, upgradefile, timeout=None):
        self._extract(upgradefile, self.middleware.entity_home,
                      self.middleware.entity_user, self.middleware.entity_group,
                      self.native, timeout)

    def revert(self, result, backupfile, timeout=None, *args, **kwargs):
        super(AppFileUpgradeBase, self).revert(result, *args, **kwargs)
        if isinstance(result, failure.Failure):
            if backupfile is None:
                LOG.info('backupfile is none, can not revert')
            else:
                self.middleware.set_return(self.taskname, common.REVERT_FAIL)
                try:
                    self._extract(backupfile, self.middleware.apppath,
                                  self.middleware.entity_user, self.middleware.entity_group,
                                  native=self.native,
                                  timeout=timeout)
                except Exception:
                    if LOG.isEnabledFor(logging.DEBUG):
                        LOG.exception('revert from %s fail' % backupfile)
                    raise
            self.middleware.set_return(self.taskname, common.REVERTED)


    def _extract(self, src, dst, user, group, native=True, timeout=None):
        waiter = zlibutils.async_extract(src, dst, exclude=self._exclude,
                                         native=native,
                                         timeout=timeout,
                                         fork=functools.partial(safe_fork, user, group)
                                         if systemutils.LINUX else None)
        waiter.wait()


class AppUpdateBase(AppTaskBase):
    """程序更新,这里的更新一般是非app文件相关的更新
    app文件更新使用AppFileUpgrade
    这里一般用于热函数调用,配置刷新等
    """


class Application(object):

    def __init__(self, middleware,
                 databases=None,
                 createtask=None,
                 deletetask=None,
                 startstak=None,
                 stoptask=None,
                 upgradetask=None,
                 updatetask=None):
        """
        @param createtask:          class: AppTaskBase 创建方法
        @param deletetask:          class: AppTaskBase 删除方法
        @param starttask:           class: AppTaskBase 启动方法
        @param stoptask:            class: AppTaskBase 关闭方法
        @param upgradetask:         class: AppTaskBase 文件更新升级
        @param updatetask:          class: AppTaskBase 升级方法(有别于upgrade, 一般用于特殊的无文件更新)
        """
        if createtask:
            if stoptask or deletetask:
                raise RuntimeError('do not input create with delete,stop')
        if deletetask:
            if upgradetask or updatetask or startstak or createtask:
                raise RuntimeError('do not input delete with create,update,upgrade,stop')
        for func in (createtask, startstak, stoptask, upgradetask, updatetask, deletetask):
            if func and not isinstance(func, AppTaskBase):
                raise RuntimeError('func type error')
        # 创建
        self.createtask = createtask
        # 删除
        self.deletetask = deletetask
        # 启动
        self.startstak = startstak
        # 停止
        self.stoptask = stoptask
        # 更新
        self.upgradetask = upgradetask
        # 更新
        self.updatetask = updatetask
        # 绑定的EntityMiddleware对象
        self.middleware = middleware
        # 绑定数据库
        self.databases = databases
