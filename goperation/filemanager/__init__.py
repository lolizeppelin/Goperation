import os
import six

from collections import namedtuple

import datetime
from eventlet import event
from eventlet.semaphore import Semaphore

from simpleutil.utils import attributes
from simpleutil.utils import digestutils
from simpleutil.utils import jsonutils
from simpleutil.utils.singleton import singleton
from simpleutil.log import log as logging

from simpleservice.ormdb.engines import create_engine
from simpleservice.ormdb.orm import get_maker
from simpleservice.ormdb.api import model_query

from goperation.filemanager import common
from goperation.filemanager import exceptions
from goperation.filemanager import models
from goperation.filemanager import downloader


LOG = logging.getLogger(__name__)

LocalFile = namedtuple('file', ['path', 'uuid', 'md5', 'crc32'])


@singleton
class FileManager(object):
    # file info schema
    SCHEMA = {
        'type': 'object',
        'required': ['address', 'ext', 'size', 'uploadtime', 'marks'],
        'properties': {
            "downloader": {'type': 'string'},
            "adapter_args": {'type': 'array'},
            "address": {'type': 'string'},
            "ext": {'type': 'string'},
            "size": {'type': 'integer'},
            "desc": {'type': 'string'},
            "uploadtime": {'type': 'string', 'format': 'date-time'},
            'marks': {
                'type': 'object',
                'properties': {
                    'uuid': {'type': 'string', 'format': 'uuid'},
                    'crc32': {'type': 'string'},
                    'md5': {'type': 'string', 'format': 'md5'},
                    },
                'required': ['uuid', 'crc32', 'md5']
            }
        }
    }

    def __init__(self, conf, threadpool, infoget):

        if not os.path.exists(conf.filecache):
            os.makedirs(conf.filecache, 0755)
        self.path = os.path.join(conf.filecache, 'files')
        self.threadpool = threadpool
        self.infoget = infoget
        self.localfiles = {}
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
        if not self.session:
            raise exceptions.FileManagerError('FileManager database session is None')
        not_match_files = []
        local_files = {}
        with self.lock:
            if self.downloading:
                raise exceptions.DownLoading('Can not scan when downlonding')
            # files in local disk
            if not os.path.exists(self.path):
                os.makedirs(self.path, 0755)
            for filename in os.listdir(self.path):
                full_path = os.path.join(self.path, filename)
                if os.path.isfile(full_path):
                    size = os.path.getsize(full_path)
                    uuid, ext = os.path.splitext(filename)
                    if len(ext) < 1 or not ext.startswith(os.extsep):
                        if strict:
                            raise RuntimeError('File with name %s ext value error' % filename)
                        continue
                    if not attributes.is_uuid_like(uuid):
                        if strict:
                            raise RuntimeError('File with name %s is not uuid' % filename)
                        continue
                    if uuid in local_files:
                        if strict:
                            raise RuntimeError('File with uuid %s is duplication' % filename)
                    local_files[uuid] = dict(size=size, ext=ext[1:])
            # files record in database
            self.localfiles.clear()
            query = model_query(self.session, models.FileDetail)
            files = query.all()
            with self.session.begin():
                for _file_detail in files:
                    filename = _file_detail.uuid + os.extsep + _file_detail.ext
                    file_path = os.path.join(self.path, filename)
                    try:
                        local_file = local_files.pop(_file_detail.uuid)
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
                    self.localfiles[file_path] = dict(crc32=_file_detail.crc32,
                                                      md5=_file_detail.md5,
                                                      uuid=_file_detail.uuid)
            with self.session.begin():
                while local_files:
                    uuid, local_file = local_files.popitem()
                    local_size = local_file['size']
                    local_ext = local_file['ext']
                    filename = uuid + os.extsep + local_ext
                    file_path = os.path.join(self.path, filename)
                    crc32 = digestutils.filecrc32(file_path)
                    md5 = digestutils.filemd5(file_path)
                    _file_detail = models.FileDetail(uuid=uuid, size=local_size,
                                                     crc32=crc32, md5=md5, ext=local_ext,
                                                     desc='add from scanning')
                    # add file record into database
                    self.session.add(_file_detail)
                    self.session.flush()
                    self.localfiles[file_path] = dict(crc32=crc32,
                                                      md5=md5,
                                                      uuid=uuid)
            # delete check fail files
            for _file in not_match_files:
                os.remove(_file)
            del not_match_files[:]

    def clean_expired(self):
        pass

    def stop(self):
        with self.lock:
            for ev in six.itervalues(self.downloading):
                try:
                    ev.wait()
                except Exception as e:
                    LOG.error('Stop file manager fail with %s' % str(e))
                    pass
            self.session.close()
            self.session = None

    def find(self, target):
        if target in self.localfiles:
            return LocalFile([target,
                              self.localfiles[target]['uuid'],
                              self.localfiles[target]['md5'],
                              self.localfiles[target]['crc32']])
        for path, marks in six.iteritems(self.localfiles):
            if target in six.itervalues(marks):
                return LocalFile([path,
                                  marks['uuid'],
                                  marks['md5'],
                                  marks['crc32']])
        raise exceptions.NoFileFound('File Manager can not find file of %s' % target)

    def get(self, target, download=True, timeout=None):
        if not self.session:
            raise exceptions.FileManagerError('File managere closed')
        try:
            return self.find(target)
        except exceptions.NoFileFound:
            if download:
                LOG.info('Try download file for %s' % target)
            else:
                raise
        if target in self.downloading:
            with self.lock:
                if not self.session:
                    raise RuntimeError('FileManager closed')
                if target in self.downloading:
                    th = self.downloading[target]
                    th.wait()
        self._download(target, timeout)
        return self.find(target)

    def _download(self, mark, timeout):
        fileinfo = self.infoget(mark)
        LOG.info('Try download file of %s' % str(fileinfo))
        jsonutils.schema_validate(fileinfo, FileManager.SCHEMA)
        uuid = fileinfo['marks']['uuid']
        uploadtime = fileinfo.get('uploadtime')
        if uploadtime:
            uploadtime = datetime.datetime.strptime(uploadtime, '%Y-%m-%d %H:%M:%S')
        if uuid in self.downloading:
            th = self.downloading[uuid]
            try:
                th.wait()
            finally:
                self.downloading.pop(uuid, None)
            return
        address = fileinfo['address']
        filename = fileinfo['marks']['uuid'] + os.extsep + fileinfo['ext']
        path = os.path.join(self.path, filename)
        ev = event.Event()
        self.downloading[uuid] = ev
        if os.path.exists(path):
            try:
                md5 = digestutils.filemd5(path)
                crc32 = digestutils.filecrc32(path)
                size = os.path.getsize(path)
                LOG.info('Download file %s already exist' % uuid)
            except Exception as e:
                LOG.error('Download get size,md5,crc32 fail')
                ev.send(exc=e)
                self.downloading.pop(uuid, None)
                raise e
        else:
            # default downloader http
            _downloader = downloader_factory(fileinfo.get('downloader', 'http'),
                                             fileinfo.get('adapter_args', []))

            # async downloading thread start
            LOG.info('Download %s with %s' % (address, _downloader.__class__.__name__))
            # th = self.threadpool.add_thread(_downloader.download, address, path, timeout)
            try:
                # md5, crc32 = th.wait()
                md5, crc32 = _downloader.download(address, path, timeout)
                size = os.path.getsize(path)
                LOG.info('Download file %s success, wirte to local database' % uuid)
            except Exception as e:
                if os.path.exists(path):
                    try:
                        os.remove(path)
                    except (OSError, IOError):
                        LOG.error('Download fail, remove path %s fail' % path)
                ev.send(exc=e)
                self.downloading.pop(uuid, None)
                raise
        try:
            if crc32 != fileinfo['marks']['crc32'] \
                    or md5 != fileinfo['marks']['md5'] \
                    or size != fileinfo['size']:
                raise exceptions.FileNotMatch('File md5 or crc32 or size not the same')
            # write into database
            file_detil = models.FileDetail(uuid=uuid, size=size,
                                           crc32=crc32, md5=md5,
                                           ext=fileinfo['ext'],
                                           desc=fileinfo.get('desc', 'unkonwn file'),
                                           address=fileinfo['address'],
                                           uploadtime=uploadtime)
            self.session.add(file_detil)
            self.session.flush()
            self.localfiles[path] = dict(uuid=uuid, crc32=crc32, md5=md5)
            ev.send(result=None)
        except Exception as e:
            ev.send(exc=e)
            raise
        finally:
            self.downloading.pop(uuid, None)

    def delete(self, target):
        try:
            localfile = self.find(target)
        except exceptions.NoFileFound:
            return
        query = model_query(self.session, models.FileDetail,
                            filter=models.FileDetail.uuid == localfile.uuid)
        fileobj = query.one_or_none()
        if fileobj:
            self.session.delete(fileobj)
            self.session.flush()
        if os.path.exists(localfile.path):
            try:
                os.remove(localfile.path)
            except (OSError, IOError):
                LOG.error('Remove file %s fail' % localfile.path)


def downloader_factory(adapter_cls, cls_args):
    if not adapter_cls.endswith('_cls'):
        adapter_cls += '_cls'
    cls = getattr(downloader, adapter_cls)
    return cls(*cls_args)
