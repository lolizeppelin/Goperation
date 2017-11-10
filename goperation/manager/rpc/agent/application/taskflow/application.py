# -*- coding: utf-8 -*-
import os
import functools

from simpleutil import system

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


class AppRemoteBackupFile(TargetFile):

    def __init__(self, source, checker=None):
        super(AppRemoteBackupFile, self).__init__(source)
        self.checker = checker

    def post_check(self):
        if self.checker:
            self.checker(self.realpath)


class AppUpgradeFile(TargetFile):

    def __init__(self, source,
                 rollback=False,
                 remote_backup=None):
        """
        @param source:                  class: dict  下载所需文件信息
        @param rollback:                class: 升级是否可以回滚
        @param remote_backup:           class: AppRemoteBackupFile 远程回滚文件
        """
        super(AppUpgradeFile, self).__init__(source)
        self.rollback = rollback
        self.remote_backup = remote_backup


class Application(object):

    def __init__(self,
                 upgrade=None,
                 backup=None,
                 startfunc=None, start_kwargs=None,
                 stopfunc=None, stop_kwargs=None,
                 killfunc=None, kill_kwargs=None,
                 updatefunc=None, update_kwargs=None):
        """
        @param upgrade:             class: AppUpgradeFile 升级文件
        @param backup:              class: string of file path 本地备份文件
        @param startfunc:           class: callable 启动方法
        @param start_kwargs:        class: dict startfunc参数
        """
        self.upgrade = upgrade
        self.backup = backup
        self.startfunc = startfunc
        self.start_kwargs = start_kwargs
        self.stopfunc = stopfunc
        self.stop_kwargs = stop_kwargs
        self.killfunc = killfunc
        self.kill_kwargs = kill_kwargs
        self.updatefunc = updatefunc
        self.update_kwargs = update_kwargs
        if self.upgrade and self.upgrade.rollback:
            if not self.upgrade.remote_backup and not self.backup:
                raise RuntimeError('application can not rollback without backup')


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


class AppStop(StandardTask):
    """程序关闭"""
    def __init__(self, middleware):
        super(AppStop, self).__init__(middleware=middleware)

    def execute(self, kill=False):
        if self.middleware.is_success(self.__class__.__name__):
            return
        if self.middleware.application.killfunc and kill:
            LOG.info('AppStop try kill endpoint %s %d' % (self.middleware.endpoint,
                                                          self.middleware.entity))
            kwargs = self.middleware.application.kill_kwargs or {}
            self.middleware.application.killfunc(self.middleware.entity,
                                                 **kwargs)
        else:
            LOG.info('AppStop try stop endpoint %s %d' % (self.middleware.endpoint,
                                                          self.middleware.entity))
            kwargs = self.middleware.application.stop_kwargs or {}
            self.middleware.application.stopfunc(self.middleware.entity,
                                                 **kwargs)


class AppUpdate(StandardTask):
    """升序更新,这里的更新一般是非app文件相关的更新
    app文件更新使用AppFileUpgrade
    这里一般用于热函数调用,配置刷新等
    """
    def __init__(self, middleware):
        super(AppUpdate, self).__init__(middleware=middleware)

    def execute(self):
        if self.middleware.is_success(self.__class__.__name__):
            return
        kwargs = self.middleware.application.update_kwargs or {}
        self.middleware.application.updatefunc(self.middleware.entity,
                                               **kwargs)


class AppStart(StandardTask):
    """程序启动"""
    def __init__(self, middleware):
        super(AppStart, self).__init__(middleware=middleware)

    def execute(self):
        if self.middleware.is_success(self.__class__.__name__):
            return
        if self.middleware.application.startfunc:
            kwargs = self.middleware.application.start_kwargs or {}
            self.middleware.application.startfunc(self.middleware.entity, **kwargs)


class AppUpgradeFileGet(StandardTask):
    """app 程序升级文件获取"""
    def __init__(self, middleware, rebind=None):
        super(AppUpgradeFileGet, self).__init__(middleware, rebind=rebind)

    def execute(self, timeout):
        if not self.middleware.application.upgrade.realpath:
            self.middleware.filemanager.get(self.middleware.application.upgrade, download=True, timeout=timeout)

    def revert(self, result, *args, **kwargs):
        super(AppUpgradeFileGet, self).revert(result, *args, **kwargs)
        if isinstance(result, failure.Failure):
            if self.middleware.application.upgrade.realpath:
                self.middleware.application.upgrade.clean()
            self.middleware.set_return(self.__class__.__name__, common.REVERTED)


class AppBackUp(StandardTask):
    """app 程序文件备份"""
    def __init__(self, middleware, rebind=None):
        super(AppBackUp, self).__init__(middleware, rebind=rebind)
        self.pwd = os.getcwd()
        self.exclude = lambda x: None

    def execute(self, timeout):
        if self.middleware.is_success(self.__class__.__name__):
            return
        # download remote backup file and check it
        if self.middleware.application.upgrade and self.middleware.application.upgrade.remote_backup:
            LOG.info('AppBackUp get remote backup file')
            self.middleware.filemanager.get(self.middleware.application.upgrade.remote_backup,
                                            download=True, timeout=timeout)
            self.middleware.application.upgrade.remote_backup.post_check()
        # dump from local application path
        if self.middleware.application.backup:
            LOG.info('AppBackUp dump local bakcup file from %s %d' % (self.middleware.endpoint,
                                                                      self.middleware.entity))
            src = os.path.join(self.middleware.entity_home, self.middleware.entity_appname)
            LOG.debug('AppBackUp dump local bakcup from path %s' % src)
            dst = self.middleware.application.backup
            async_compress(src, dst, exclude=self.exclude,
                           fork=functools.partial(safe_fork,
                                                  user=self.middleware.entity_user,
                                                  group=self.middleware.entity_group) if system.LINUX else None,
                           timeout=timeout)
        if not system.LINUX:
            os.chdir(self.pwd)

    def revert(self, result, *args, **kwargs):
        super(AppBackUp, self).revert(result, *args, **kwargs)
        if isinstance(result, failure.Failure):
            if not system.LINUX:
                os.chdir(self.pwd)
            # delete remote backup file
            if self.middleware.application.upgrade.remote_backup:
                self.middleware.application.upgrade.remote_backup.clean()
            # delete local backup file
            if self.middleware.application.backup \
                    and os.path.exists(self.middleware.application.backup):
                os.remove(self.middleware.application.backup)
            self.middleware.set_return(self.__class__.__name__, common.REVERTED)


class AppFileUpgrade(StandardTask):
    """app 程序文件升级"""
    def __init__(self, middleware, rebind=None):
        super(AppFileUpgrade, self).__init__(middleware, rebind=rebind)

    def execute(self, timeout):
        if self.middleware.is_success(self.__class__.__name__):
            return
        LOG.info('AppFileUpgrade extract file for %s %d' % (self.middleware.endpoint,
                                                            self.middleware.entity))
        src = self.middleware.application.upgrade.realpath
        dst = os.path.join(self.middleware.entity_home, self.middleware.entity_appname)
        async_extract(src, dst,
                      fork=functools.partial(safe_fork,
                                             user=self.middleware.entity_user,
                                             group=self.middleware.entity_group) if system.LINUX else None,
                      timeout=timeout)

    def revert(self, result, *args, **kwargs):
        super(AppFileUpgrade, self).revert(result, *args, **kwargs)
        if isinstance(result, failure.Failure) or self.middleware.application.upgrade.rollback:
            LOG.info('AppFileUpgrade Try revert')
            # revert from remote backup first
            if self.middleware.application.upgrade.remote_backup:
                src = self.middleware.application.upgrade.remote_backup.file
            # revert from local backup
            elif self.middleware.application.backup:
                src = self.middleware.application.backup
            else:
                raise RuntimeError('Revert AppFileUpgrade fail, not backup file found')
            dst = self.middleware.entity_home
            async_extract(src, dst,
                          fork=functools.partial(safe_fork,
                                                 user=self.middleware.entity_user,
                                                 group=self.middleware.entity_group) if system.LINUX else None)
            self.middleware.set_return(self.__class__.__name__, common.REVERTED)
