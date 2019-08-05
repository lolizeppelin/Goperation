import os
import six

from collections import namedtuple

import time
import datetime
import eventlet
from eventlet import event
from eventlet.semaphore import Semaphore

from simpleutil import systemutils
from simpleutil.utils import attributes
from simpleutil.utils import digestutils
from simpleutil.utils import jsonutils
from simpleutil.utils.singleton import singleton
from simpleutil.log import log as logging

from simpleservice.ormdb.engines import create_engine
from simpleservice.ormdb.orm import get_maker
from simpleservice.ormdb.api import model_query

from goperation.filemanager import common
from goperation.filemanager import common
from goperation.filemanager import exceptions
from goperation.filemanager import models
from goperation.filemanager import downloader


LOG = logging.getLogger(__name__)

LocalFile = namedtuple('file', ['path', 'md5', 'size'])


@singleton
class FileManager(object):
    # file info schema
    SCHEMA = {
        'type': 'object',
        'required': ['address', 'ext', 'size', 'uploadtime', 'md5'],
        'properties': {
            "downloader": {'type': 'string'},
            "adapter_args": {'type': 'array'},
            "address": {'type': 'string'},
            "ext": {'type': 'string'},
            "size": {'type': 'integer'},
            "desc": {'type': 'string'},
            "uploadtime": {'type': 'string', 'format': 'date-time'},
            'md5': {'type': 'string', 'format': 'md5'},
        }
    }

    def __init__(self, conf, threadpool, infoget):

        if not os.path.exists(conf.filecache):
            os.makedirs(conf.filecache, 0o755)
        self.path = os.path.join(conf.filecache, 'files')
        self.threadpool = threadpool
        self.infoget = infoget
        self.localpath = {}
        self.localmd5 = {}
        self.downloading = {}
        self.lock = Semaphore()
        # init sqlite session
        engine = create_engine(sql_connection='sqlite:///%s' % os.path.join(conf.filecache, 'filemanager.db'),
                               logging_name='filemanager')
        if not engine.has_table(models.FileDetail.__tablename__):
            # create table if needed
            models.FileManagerTables.metadata.create_all(engine)
        session_maker = get_maker(engine)
        self.session = session_maker()

    def scanning(self, strict=False):
        not_match_files = []
        localfiles = {}
        with self.lock:
            if self.downloading:
                raise exceptions.DownLoading('Can not scan when downlonding')
            # clean all saved
            self.localpath.clear()
            self.localmd5.clear()

            # find files in local disk
            if not os.path.exists(self.path):
                os.makedirs(self.path, 0o755)
            for filename in os.listdir(self.path):
                full_path = os.path.join(self.path, filename)
                if os.path.isfile(full_path):
                    size = os.path.getsize(full_path)
                    md5, ext = os.path.splitext(filename)
                    if len(ext) < 1 or not ext.startswith(os.extsep):
                        if strict:
                            raise RuntimeError('File with name %s ext value error' % filename)
                        continue
                    if not attributes.is_md5_like(md5):
                        if strict:
                            raise RuntimeError('File with name %s is not md5' % filename)
                        continue
                    if md5 in localfiles:
                        if strict:
                            raise RuntimeError('File with md5 %s is duplication' % filename)
                    localfiles[md5] = dict(size=size, ext=ext[1:])

            # files record in database
            query = model_query(self.session, models.FileDetail)
            files = query.all()
            with self.session.begin():
                for _file_detail in files:
                    filename = _file_detail.md5 + os.extsep + _file_detail.ext
                    file_path = os.path.join(self.path, filename)
                    # diff local file with recode
                    try:
                        local_file = localfiles.pop(_file_detail.md5)
                        local_size = local_file['size']
                        local_ext = local_file['ext']
                        if local_size != _file_detail.size or local_ext != _file_detail.ext:
                            not_match_files.append(file_path)
                            self.session.delete(_file_detail)
                            self.session.flush()
                            continue
                    except KeyError:
                        # delete no exist file from database
                        self.session.delete(_file_detail)
                        self.session.flush()
                        continue
                    localfile = LocalFile(file_path, _file_detail.md5, _file_detail.size)
                    self.localpath[file_path] = localfile
                    self.localmd5[_file_detail.md5] = localfile

            with self.session.begin():
                while localfiles:
                    md5, _fileinfo = localfiles.popitem()
                    local_size = _fileinfo['size']
                    local_ext = _fileinfo['ext']
                    filename = md5 + os.extsep + local_ext
                    file_path = os.path.join(self.path, filename)
                    md5 = digestutils.filemd5(file_path)
                    _file_detail = models.FileDetail(size=local_size, md5=md5, ext=local_ext,
                                                     desc='add from scanning')
                    # add file record into database
                    self.session.add(_file_detail)
                    self.session.flush()
                    localfile = LocalFile(file_path, md5, local_size)
                    self.localpath[file_path] = localfile
                    self.localmd5[_file_detail.md5] = localfile
            # delete check fail files
            for _file in not_match_files:
                os.remove(_file)
            del not_match_files[:]

    def clean_expired(self, day=10):
        timeline = day * 86400
        now = int(time.time())
        targets = self.localmd5.keys()
        for md5 in targets:
            localfile = self.localmd5[md5]
            if (now - systemutils.acctime(localfile.path)) > timeline:
                self.delete(md5)
            eventlet.sleep(0)

    def stop(self):
        with self.lock:
            for ev in six.itervalues(self.downloading):
                try:
                    ev.wait()
                except Exception as e:
                    LOG.error('Stop file manager fail with %s' % str(e))
            self.session.close()
            self.session = None

    def _find(self, target):
        try:
            localfile = self.localmd5[target]
        except KeyError:
            try:
                localfile = self.localpath[target]
            except KeyError:
                raise exceptions.NoFileFound('File Manager can not find file of %s' % target)
        return localfile

    def find(self, target):
        localfile = self._find(target)
        if os.path.exists(localfile.path):
            systemutils.touch(localfile.path)
        else:
            raise exceptions.FileIsMiss('File Manager find file is miss')
        return localfile

    def get(self, target, download=True, timeout=None):
        try:
            localfile = self.find(target)
            md5 = localfile.md5
        except exceptions.NoFileFound:
            if download:
                LOG.info('Try download file for %s' % target)
                md5 = target
            else:
                raise
        except exceptions.FileIsMiss:
            if not download:
                self.delete(target)
                raise
            localfile = self._find(target)
            md5 = localfile.md5

        with self.lock:
            if not self.session:
                raise exceptions.FileManagerError('FileManager Stoped')
            if md5 not in self.downloading:
                th = self._download(md5, timeout)
            else:
                th = self.downloading[md5]
        th.wait()
        return self.find(md5)

    def _download(self, md5, timeout):
        if not attributes.is_md5_like(md5):
            raise ValueError('%s is not md5, can not download' % md5)
        try:
            return self.downloading[md5]
        except KeyError:
            ev = event.Event()
            self.downloading[md5] = ev

        fileinfo = self.infoget(md5)
        LOG.debug('Try download file of %s', str(fileinfo))
        jsonutils.schema_validate(fileinfo, FileManager.SCHEMA)

        if md5 != fileinfo['md5']:
            self.downloading.pop(md5, None)
            ev.send(exc=exceptions.FileManagerError('Md5 not the same!'))
            raise exceptions.FileManagerError('Md5 not the same!')

        def __download():

            address = fileinfo['address']
            filename = fileinfo['md5'] + os.extsep + fileinfo['ext']
            path = os.path.join(self.path, filename)

            if os.path.exists(path):
                LOG.info('Output file %s alreday exist' % path)
                try:
                    _md5 = digestutils.filemd5(path)
                    size = os.path.getsize(path)
                except (OSError, IOError) as e:
                    LOG.error('Download get size,md5 fail')
                    ev.send(exc=e)
                    self.downloading.pop(fileinfo['md5'], None)
                    raise e
            else:
                # default downloader http
                _downloader = downloader_factory(fileinfo.get('downloader', 'http'),
                                                 fileinfo.get('adapter_args', []))
                LOG.info('Download %s with %s' % (address, _downloader.__class__.__name__))
                try:
                    _md5 = _downloader.download(address, path, timeout)
                    size = os.path.getsize(path)
                    LOG.info('Download file %s success, wirte to local database' % fileinfo['md5'])
                except Exception as e:
                    if os.path.exists(path):
                        try:
                            os.remove(path)
                        except (OSError, IOError):
                            LOG.error('Download fail, remove path %s fail' % path)
                    self.downloading.pop(fileinfo['md5'], None)
                    ev.send(exc=e)
                    raise e
            try:
                if _md5 != fileinfo['md5'] or size != fileinfo['size']:
                    if os.path.exists(path):
                        try:
                            os.remove(path)
                        except (OSError, IOError):
                            LOG.error('Download fail, remove path %s fail' % path)
                    raise exceptions.FileNotMatch('File md5 or size not the same')
                # write into database
                uploadtime = fileinfo.get('uploadtime')
                if uploadtime:
                    uploadtime = datetime.datetime.strptime(uploadtime, '%Y-%m-%d %H:%M:%S')
                try:
                    localfile = self.localmd5[md5]
                except KeyError:
                    file_detil = models.FileDetail(md5=md5, size=size,
                                                   ext=fileinfo['ext'],
                                                   desc=fileinfo.get('desc', 'unkonwn file'),
                                                   address=fileinfo['address'],
                                                   uploadtime=uploadtime)
                    self.session.add(file_detil)
                    self.session.flush()
                    localfile = LocalFile(path, md5, size)
                    self.localpath[path] = localfile
                    self.localmd5[md5] = localfile
                if localfile.size != size:
                    try:
                        os.remove(path)
                    except (OSError, IOError):
                        LOG.error('Download file size not match')
                    raise exceptions.FileManagerError('Size not match')
                self.downloading.pop(md5, None)
                ev.send(result=None)
            except Exception as e:
                self.downloading.pop(md5, None)
                ev.send(exc=e)
                raise

        self.threadpool.add_thread_n(__download)
        return ev

    def delete(self, target):
        try:
            localfile = self._find(target)
        except exceptions.NoFileFound:
            return
        query = model_query(self.session, models.FileDetail,
                            filter=models.FileDetail.md5 == localfile.md5)
        with self.lock:
            try:
                fileobj = query.one_or_none()
                if fileobj:
                    self.session.delete(fileobj)
                    self.session.flush()
                if os.path.exists(localfile.path):
                    os.remove(localfile.path)
            except (OSError, IOError):
                LOG.error('Remove file %s fail' % localfile.path)
            finally:
                self.localpath.pop(localfile.path, None)
                self.localmd5.pop(localfile.md5, None)


def downloader_factory(adapter_cls, cls_args):
    if not adapter_cls.endswith('_cls'):
        adapter_cls += '_cls'
    cls = getattr(downloader, adapter_cls)
    return cls(*cls_args)
