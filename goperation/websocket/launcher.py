# -*- coding:utf-8 -*-
import functools
import os
import subprocess
import sys

import eventlet
import psutil
from eventlet import hubs

from simpleutil.log import log as logging
from simpleutil.utils import systemutils
from simpleutil.utils import uuidutils
from simpleutil.utils import jsonutils

from simpleutil.utils.systemutils import ExitBySIG
from simpleutil.utils.systemutils import UnExceptExit

import goperation
from goperation.common import FILEINFOSCHEMA
from goperation.utils import safe_fork
from goperation.websocket import exceptions


LOG = logging.getLogger(__name__)


class LaunchRecverWebsocket(object):

    def __init__(self, executer):
        self.executer = executer

        self.tmp = None

        self.size = 0
        self.output = None

        self.timer = None
        self.pid = None

    def upload(self, user, group, ipaddr, port, rootpath, fileinfo, logfile, timeout):
        jsonutils.schema_validate(fileinfo, FILEINFOSCHEMA)
        if timeout:
            timeout = int(timeout)
        if timeout > 7200:
            raise ValueError('Timeout over 7200 seconds')
        with goperation.tlock(self.executer):
            logfile = logfile or os.devnull
            executable = systemutils.find_executable(self.executer)
            token = str(uuidutils.generate_uuid()).replace('-', '')
            args = [executable, '--home', rootpath, '--token', token, '--port', str(port)]

            ext = fileinfo.get('ext') or os.path.splitext(fileinfo.get('filename'))[1][1:]
            if ext.startswith('.'):
                ext = ext[1:]
            if not ext:
                raise exceptions.PreWebSocketError('ext is empty')

            filename = '%s.%s' % (fileinfo.get('md5'), ext)
            self.output = os.path.join(rootpath, filename)
            # 判断文件是否存在
            if os.path.exists(self.output):
                raise exceptions.PreWebSocketError('file exist with same name')
            self.size = fileinfo.get('size')
            # 准备文件目录
            path = os.path.dirname(self.output)
            if not os.path.exists(path):
                os.makedirs(path, mode=0o775)
                if user or group:
                    os.chown(path, user, group)
            else:
                if not os.path.isdir(path):
                    raise exceptions.PreWebSocketError('prefix path is not dir')

            if not ext or ext == 'tmp':
                raise exceptions.PreWebSocketError('Can not find file ext or ext is tmp')
            # 临时文件名
            self.tmp = os.path.join(rootpath, '%s.tmp' % str(uuidutils.generate_uuid()).replace('-', ''))
            args.extend(['--outfile', self.tmp])
            args.extend(['--md5', fileinfo.get('md5')])
            args.extend(['--size', str(fileinfo.get('size'))])
            args.extend(['--log-file', logfile])
            args.extend(['--loglevel', 'info'])

            changeuser = functools.partial(systemutils.drop_privileges, user, group)

            with open(os.devnull, 'wb') as f:
                LOG.debug('Websocket command %s %s' % (executable, ' '.join(args)))
                if systemutils.WINDOWS:
                    sub = subprocess.Popen(executable=executable, args=args,
                                           stdout=f.fileno(), stderr=f.fileno(),
                                           close_fds=True, preexec_fn=changeuser)
                    pid = sub.pid
                else:
                    pid = safe_fork(user=user, group=group)
                    if pid == 0:
                        os.dup2(f.fileno(), sys.stdout.fileno())
                        os.dup2(f.fileno(), sys.stderr.fileno())
                        os.closerange(3, systemutils.MAXFD)
                        try:
                            os.execv(executable, args)
                        except OSError:
                            os._exit(1)
                LOG.info('Websocket recver start with pid %d' % pid)

            def _kill():
                try:
                    p = psutil.Process(pid=pid)
                    name = p.name()
                except psutil.NoSuchProcess:
                    return
                if name == self.executer:
                    LOG.warning('Websocket recver overtime, kill it')
                    p.kill()

            self.pid = pid
            hub = hubs.get_hub()
            self.timer = hub.schedule_call_global(timeout or 3600, _kill)

            return dict(port=port, token=token, ipaddr=ipaddr, filename=filename)

    def syncwait(self, exitfunc=None, notify=None):
        try:
            try:
                if systemutils.POSIX:
                    from simpleutil.utils.systemutils import posix
                    posix.wait(self.pid)
                else:
                    systemutils.subwait(self.pid)
            except (ExitBySIG, UnExceptExit) as e:
                LOG.error('Websocket process wait catch error %s' % e.message)
                os.remove(self.tmp)
            finally:
                LOG.info('Websocket process with pid %d has been exit' % self.pid)
                self.timer.cancel()
            if not os.path.exists(self.tmp):
                LOG.error('Upload file fail, %s not exist, has been delete' % self.tmp)
                notify & eventlet.spawn_n(notify.fail)
                raise exceptions.PostWebSocketError('File not exit after upload')
            if os.path.getsize(self.tmp) != self.size:
                notify & eventlet.spawn_n(notify.fail)
                LOG.error('Size not match')
                os.remove(self.tmp)
                raise exceptions.PostWebSocketError('File size not match after upload')
            LOG.info('Upload file end, success')
            if os.path.exists(self.output):
                LOG.error('Out put file exist?')
                os.remove(self.output)
            os.rename(self.tmp, self.output)
            notify & eventlet.spawn_n(notify.success)
        finally:
            LOG.info('Call exit func')
            exitfunc & exitfunc()

    def asyncwait(self, exitfunc=None, notify=None):
        eventlet.spawn_n(self.syncwait, exitfunc, notify)
