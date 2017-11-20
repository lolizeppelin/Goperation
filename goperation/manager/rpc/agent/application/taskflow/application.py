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
    """app 程序升级文件获取"""
    def __init__(self, middleware, upgradefile, rebind=None):
        super(AppUpgradeFileGet, self).__init__(middleware, rebind=rebind, provides='upgradefile')

    def execute(self, timeout):
        if self.middleware.is_success(self.__class__.__name__):
            return
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
    def __init__(self, middleware, backupfile, rebind=None):
        super(AppBackUp, self).__init__(middleware, rebind=rebind, provides='backupfile')
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

    def revert(self, result, *args, **kwargs):
        super(AppBackUp, self).revert(result, *args, **kwargs)
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


class AppFunctionWapper(object):

    def __init__(self, execute, kwargs,
                 revert=None, rollback=False):
        if rollback and not revert:
            raise ValueError('AppFunctionWapper rollback need revert')
        self.execute = execute
        self.kwargs = kwargs
        self.revert = revert
        self.rollback = rollback


class AppTaskBase(StandardTask):

    def __init__(self, middleware, rebind=None, requires=None, revert_requires=None, wapper=None, kwargs=None):
        super(AppTaskBase, self).__init__(middleware=middleware, rebind=rebind,
                                          requires=requires, revert_requires=revert_requires)
        if wapper and not isinstance(wapper, AppFunctionWapper):
            raise RuntimeError('AppTaskBase need a AppFunctionWapper')
        self.wapper = wapper
        self.kwargs = kwargs or {}

    def execute(self, **kwargs):
        if not self.wapper:
            raise NotImplementedError('AppTaskBase execute wapper is None')
        if self.middleware.is_success(self.__class__.__name__):
            return
        kwargs.update(self.kwargs)
        self.wapper.execute(self.middleware, **kwargs)

    def revert(self, result, *args, **kwargs):
        super(AppTaskBase, self).revert(result, *args, **kwargs)
        if isinstance(result, failure.Failure) or self.wapper.rollback:
            if self.wapper.revert:
                self.middleware.set_return(self.__class__.__name__, common.REVERT_FAIL)
                try:
                    self.wapper.revert(self.middleware, result, **kwargs)
                except DoNotNeedRevert:
                    self.middleware.set_return(self.__class__.__name__, common.EXECUTE_FAIL)
                else:
                    self.middleware.set_return(self.__class__.__name__, common.REVERTED)


class AppStop(AppTaskBase):
    """程序关闭"""


class AppUpdate(AppTaskBase):
    """程序更新,这里的更新一般是非app文件相关的更新
    app文件更新使用AppFileUpgrade
    这里一般用于热函数调用,配置刷新等
    """


class AppStart(AppTaskBase):
    """程序启动"""


class AppFileUpgrade(AppTaskBase):
    """app 程序文件升级"""


class ExtarctUpgrade(AppFunctionWapper):
    """解压升级程序"""

    def __init__(self, upgrade, rollback=False):
        super(ExtarctUpgrade, self).__init__(execute=self._execute, kwargs=None,
                                             revert=self._revert,
                                             rollback=rollback)

    def _execute(self, middleware, timeout, upgradefile):
        self._extract(upgradefile, middleware.entity_home,
                      middleware.entity_user, middleware.entity_group,
                      timeout)

    def _revert(self, middleware, result, backupfile, timeout=None):
        if backupfile is None:
            raise DoNotNeedRevert
        self._extract(backupfile, middleware.entity_home,
                      middleware.entity_user, middleware.entity_group,
                      timeout)

    def _extract(self, src, dst, user, group, timeout):
        async_extract(src, dst, fork=functools.partial(safe_fork, user, group) if systemutils.LINUX else None,
                      timeout=timeout)


class Application(object):

    def __init__(self,
                 createfunc=None, create_kwargs=None,
                 deletefunc=None, delete_kwargs=None,
                 startfunc=None, start_kwargs=None,
                 stopfunc=None, stop_kwargs=None,
                 upgradefunc=None, upgrade_kwargs=None,
                 updatefunc=None, update_kwargs=None):
        """
        @param createfunc:          class: createfunc 创建方法
        @param create_kwargs:       class: dict createfunc参数
        @param deletefunc:          class: deletefunc 删除方法
        @param delete_kwargs:       class: dict deletefunc参数
        @param startfunc:           class: callable 启动方法
        @param start_kwargs:        class: dict startfunc参数
        @param stopfunc:            class: callable 关闭方法
        @param stop_kwargs:         class: dict stopfunc参数
        @param killfunc:            class: callable 强制关闭方法
        @param kill_kwargs:         class: dict killfunc参数
        @param upgradefunc:         class: callable 文件更新升级
        @param upgrade_kwargs:      class: dict upgradefunc参数
        @param updatefunc:          class: callable 升级方法(有别于upgrade, 一般用于特殊的无文件更新)
        @param update_kwargs:       class: dict updatefunc参数
        """
        if createfunc:
            if not isinstance(createfunc, AppFunctionWapper):
                raise RuntimeError('create func type error')
            if upgradefunc or updatefunc or stopfunc or deletefunc:
                raise RuntimeError('do not input create with delete,update,upgrade,stop')
        if deletefunc:
            if not isinstance(deletefunc, AppFunctionWapper):
                raise RuntimeError('delete func type error')
            if upgradefunc or updatefunc or startfunc or createfunc:
                raise RuntimeError('do not input delete with create,update,upgrade,stop')
        for func in (startfunc, stopfunc, updatefunc, updatefunc):
            if func and not isinstance(func, AppFunctionWapper):
                raise RuntimeError('func type error')
        # 创建
        self.createfunc = createfunc
        self.create_kwargs = create_kwargs
        # 删除
        self.deletefunc = deletefunc
        self.delete_kwargs = delete_kwargs
        # 启动
        self.startfunc = startfunc
        self.start_kwargs = start_kwargs
        # 停止
        self.stopfunc = stopfunc
        self.stop_kwargs = stop_kwargs
        # 更新
        self.upgradefunc = upgradefunc
        self.upgrade_kwargs = upgrade_kwargs
        # 更新
        self.updatefunc = updatefunc
        self.update_kwargs = update_kwargs
