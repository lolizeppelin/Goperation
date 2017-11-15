import functools
import webob.exc


from simpleutil.common.exceptions import InvalidArgument
from simpleutil.log import log as logging
from simpleutil.utils import jsonutils
from simpleutil.utils import uuidutils
from simpleutil.utils import timeutils
from simpleutil.utils import singleton

from simpleservice.ormdb.api import model_query
from simpleservice.rpc.exceptions import AMQPDestinationNotFound
from simpleservice.rpc.exceptions import MessagingTimeout
from simpleservice.rpc.exceptions import NoSuchMethod

from goperation import threadpool
from goperation.utils import safe_func_wrapper
from goperation.manager import common as manager_common
from goperation.manager import resultutils
from goperation.manager import targetutils
from goperation.manager.api import get_session
from goperation.manager.models import DownFile
from goperation.manager.wsgi.contorller import BaseContorller
from goperation.manager.wsgi.exceptions import RpcPrepareError
from goperation.manager.wsgi.exceptions import RpcResultError


LOG = logging.getLogger(__name__)

FAULT_MAP = {InvalidArgument: webob.exc.HTTPClientError,
             NoSuchMethod: webob.exc.HTTPNotImplemented,
             AMQPDestinationNotFound: webob.exc.HTTPServiceUnavailable,
             MessagingTimeout: webob.exc.HTTPServiceUnavailable,
             RpcResultError: webob.exc.HTTPInternalServerError,
             RpcPrepareError: webob.exc.HTTPInternalServerError,
             }


@singleton.singleton
class FileReuest(BaseContorller):


    def index(self, req):
        session = get_session(readonly=True)
        query = model_query(session, DownFile)
        return resultutils.results(result='list file success',
                                   data=[downfile.to_dict() for downfile in query.all()])

    def create(self, req, body):
        try:
            address = body.pop('address')
            size = body.pop('size')
            md5 = body.pop('md5')
            crc32 = body.pop('crc32')
        except KeyError:
            raise InvalidArgument('Add file miss some keywords')
        ext = body.get('ext')
        if not ext:
            ext = address.split('.')[-1]
        downfile = DownFile(md5=md5,
                            crc32=crc32,
                            downloader=body.get('downloader', 'http'),
                            adapter_args=body.get('adapter_args'),
                            address=address,
                            ext=ext,
                            size=size,
                            desc=body.get('desc'),
                            uploadtime=body.get('uploadtime', timeutils.utcnow())
                            )
        return resultutils.results(result='Add file success', data=[dict(uuid=downfile.uuid,
                                                                         md5=downfile.md5,
                                                                         crc32=downfile.crc32,
                                                                         size=downfile.size,
                                                                         uploadtime=downfile.uploadtime,
                                                                         downloader=downfile.downloader)])

    def show(self, req, file_id):
        session = get_session(readonly=True)
        query = model_query(session, DownFile)
        if uuidutils.is_uuid_like(file_id):
            query = query.filter_by(uuid=file_id)
        elif jsonutils.is_md5_like(file_id):
            query = query.filter_by(md5=file_id)
        elif jsonutils.is_crc32_like(file_id):
            query = query.filter_by(crc32=file_id)
        else:
            raise InvalidArgument('File id not uuid or md5 or crc32')
        downfile = query.one_or_none()
        if not downfile:
            return resultutils.results(resultcode=manager_common.RESULT_ERROR, result='Get file fail, no found')
        file_info = {'downloader': downfile.downloader,
                     'address': downfile.address,
                     'ext': downfile.ext,
                     'size': downfile.size,
                     'uploadtime': downfile.uploadtime,
                     'marks': {'uuid': downfile.address,
                               'md5': downfile.md5,
                               'crc32': downfile.crc32}}
        if downfile.adapter_args:
            file_info.setdefault('adapter_args', downfile.adapter_args)
        if downfile.desc:
            file_info.setdefault('desc', downfile.desc)
        return resultutils.results(result='Get file success', data=[downfile, ])

    def delete(self, req, file_id, body):
        session = get_session()
        query = model_query(session, DownFile)
        if uuidutils.is_uuid_like(file_id):
            query = query.filter_by(uuid=file_id)
        elif jsonutils.is_md5_like(file_id):
            query = query.filter_by(md5=file_id)
        elif jsonutils.is_crc32_like(file_id):
            query = query.filter_by(crc32=file_id)
        else:
            raise InvalidArgument('File id not uuid or md5 or crc32')
        with session.begin(subtransactions=True):
            downfile = query.one_or_none()
            if not downfile:
                return resultutils.results(result='Delete file do nothing, not found')
            query.delete()

        return resultutils.results(result='Delete file success', data=[dict(uuid=downfile.uuid,
                                                                            md5=downfile.md5,
                                                                            crc32=downfile.crc32,
                                                                            size=downfile.size,
                                                                            uploadtime=downfile.uploadtime,
                                                                            downloader=downfile.downloader)])

    def send(self, req, agent_id, file_id, body=None):
        """call by client, and asyncrequest
        send file to agents
        """
        body = body or {}
        asyncrequest = self.create_asyncrequest(body)
        target = targetutils.target_all(fanout=True)
        rpc_method = 'getfile'
        rpc_args = {'mark': file_id,  'timeout': asyncrequest.deadline-1}
        rpc_ctxt = {}
        if agent_id != 'all':
            rpc_ctxt.setdefault('agents', self.agents_id_check(agent_id))
        def wapper():
            self.send_asyncrequest(asyncrequest, target,
                                   rpc_ctxt, rpc_method, rpc_args)
        threadpool.add_thread(safe_func_wrapper, wapper, LOG)
        return resultutils.results(result='Send file to agents thread spawning',
                                   data=[asyncrequest.to_dict()])


    @BaseContorller.AgentIdformater
    def list(self, req, agent_id, body):
        """call by client, and asyncrequest
        list file in agents
        """
        raise NotImplementedError

    @BaseContorller.AgentIdformater
    def clean(self, req, agent_id, file_id, body):
        """call by client, and asyncrequest
        delete file from agents
        """
        raise NotImplementedError
