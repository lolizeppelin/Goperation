# -*- coding: utf-8 -*-
import os
import functools

from simpleutil.utils import systemutils

from simpleflow.retry import Retry
from simpleflow.retry import REVERT
from simpleflow.retry import RETRY
from simpleflow.types import failure

from zlibstream.tobuffer import async_compress
from zlibstream.tofile import async_extract

from goperation.utils import safe_fork
from goperation.filemanager import TargetFile
from goperation.taskflow import common
from goperation.manager.rpc.agent.application import taskflow
from goperation.manager.rpc.agent.application.taskflow.base import StandardTask

LOG = taskflow.LOG


class DoNotNeedRevert(Exception):
    """do not need revert"""


class AppRemoteBackupFile(TargetFile):

    def __init__(self, source, checker=None):
        super(AppRemoteBackupFile, self).__init__(source)
        self.checker = checker

    def post_check(self):
        if self.checker:
            self.checker(self.realpath)


class AppUpgradeFile(TargetFile):

    def __init__(self, source,
                 remote_backup=None):
        """
        @param source:                  class: dict  下载所需文件信息
        @param remote_backup:           class: AppRemoteBackupFile 远程回滚文件
        """
        super(AppUpgradeFile, self).__init__(source)
        self.remote_backup = remote_backup


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
        if self.middleware.is_success(self.__class__.__name__):
            return
        if not self.upgradefile.realpath:
            self.middleware.filemanager.get(self.upgradefile, download=True, timeout=timeout)
        return self.upgradefile.realpath

    def revert(self, result, *args, **kwargs):
        super(AppUpgradeFileGet, self).revert(result, **kwargs)
        if isinstance(result, failure.Failure):
            if self.middleware.application.upgrade.realpath:
                self.middleware.set_return(self.__class__.__name__, common.REVERT_FAIL)
                self.middleware.application.upgrade.clean()
            self.middleware.set_return(self.__class__.__name__, common.REVERTED)


class AppBackUp(StandardTask):
    """app 程序文件备份, 默认提供参数backupfile"""
    def __init__(self, middleware, backupfile, rebind=None, provides='backupfile'):
        super(AppBackUp, self).__init__(middleware, rebind=rebind, provides=provides)
        self.pwd = os.getcwd()
        self.backupfile = backupfile
        self.exclude = lambda x: None

    def execute(self, timeout):
        if self.middleware.is_success(self.__class__.__name__):
            return
        # download remote backup file and check it
        if isinstance(self.backupfile, AppRemoteBackupFile):
            LOG.info('AppBackUp get remote backup file')
            self.middleware.filemanager.get(self.backupfile,
                                            download=True, timeout=timeout)
            self.backupfiles.post_check()
            backupfile = self.backupfile.realpath
        # dump from local application path
        elif isinstance(self.backupfile, basestring):
            LOG.info('AppBackUp dump local bakcup file from %s %d' % (self.middleware.endpoint,
                                                                      self.middleware.entity))
            src = os.path.join(self.middleware.entity_home, self.middleware.entity_appname)
            LOG.debug('AppBackUp dump local bakcup from path %s' % src)
            dst = self.backupfile
            async_compress(src, dst, exclude=self.exclude,
                           fork=functools.partial(safe_fork,
                                                  user=self.middleware.entity_user,
                                                  group=self.middleware.entity_group) if systemutils.LINUX else None,
                           timeout=timeout)
            backupfile = self.backupfile
        else:
            raise TypeError('AppBackUp find backupfile type error')
        if not systemutils.LINUX:
            os.chdir(self.pwd)
        return backupfile

    def revert(self, result, **kwargs):
        super(AppBackUp, self).revert(result, **kwargs)
        if isinstance(result, failure.Failure):
            if not systemutils.LINUX:
                os.chdir(self.pwd)
            # delete remote backup file
            if isinstance(self.backupfile, AppRemoteBackupFile):
                self.backupfile.clean()
            # delete local backup file
            elif isinstance(self.backupfile, basestring):
                if os.path.exists(self.backupfile):
                    os.remove(self.middleware.application.backup)
            self.middleware.set_return(self.__class__.__name__, common.REVERTED)


class AppTaskBase(StandardTask):
    """For Application task"""
    def __init__(self, middleware, revertable=False, rollback=False,
                 provides=None,
                 rebind=None, requires=None,
                 revert_rebind=None, revert_requires=None):
        super(AppTaskBase, self).__init__(middleware, provides=provides,
                                          rebind=rebind, requires=requires,
                                          revert_rebind=revert_rebind, revert_requires=revert_requires)
        if self.rollback and not self.revertable:
            raise RuntimeError('AppTask rollback need revertable')
        self.revertable = revertable
        self.rollback = rollback


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

    def __init__(self, middleware, revertable=False, rollback=False,
                 rebind=None, requires='upgradefile',
                 revert_requires='backupfile'):
            super(AppFileUpgradeBase, self).__init__(middleware=middleware,
                                                     revertable=revertable, rollback=rollback,
                                                     rebind=rebind, requires=requires,
                                                     revert_requires=revert_requires)

    def execute(self, upgradefile, timeout, **kwargs):
        self._extract(upgradefile, self.middleware.entity_home,
                      self.middleware.entity_user, self.middleware.entity_group,
                      timeout)

    def revert(self, result, backupfile, timeout, **kwargs):
        super(AppFileUpgradeBase, self).revert(result, **kwargs)
        self._extract(backupfile, self.middleware.entity_home,
                      self.middleware.entity_user, self.middleware.entity_group,
                      timeout)

    def _extract(self, src, dst, user, group, timeout):
        async_extract(src, dst, fork=functools.partial(safe_fork, user, group) if systemutils.LINUX else None,
                      timeout=timeout)


class AppUpdateBase(AppTaskBase):
    """程序更新,这里的更新一般是非app文件相关的更新
    app文件更新使用AppFileUpgrade
    这里一般用于热函数调用,配置刷新等
    """


class Application(object):

    def __init__(self,
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
            if not isinstance(createtask, AppTaskBase):
                raise RuntimeError('create func type error')
            if stoptask or deletetask:
                raise RuntimeError('do not input create with delete,stop')
        if deletetask:
            if not isinstance(deletetask, AppTaskBase):
                raise RuntimeError('delete func type error')
            if upgradetask or updatetask or startstak or createtask:
                raise RuntimeError('do not input delete with create,update,upgrade,stop')
        for func in (startstak, stoptask, upgradetask, updatetask):
            if func and not isinstance(func, AppTaskBase):
                raise RuntimeError('func type error')
        # 创建
        self.createftask = createtask
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
