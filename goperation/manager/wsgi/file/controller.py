import webob.exc


from simpleutil.common.exceptions import InvalidArgument
from simpleutil.log import log as logging
from simpleutil.utils import jsonutils
from simpleutil.utils import uuidutils
from simpleutil.utils import attributes
from simpleutil.utils import timeutils
from simpleutil.utils import singleton

from simpleservice.ormdb.api import model_query
from simpleservice.rpc.exceptions import AMQPDestinationNotFound
from simpleservice.rpc.exceptions import MessagingTimeout
from simpleservice.rpc.exceptions import NoSuchMethod

from goperation import threadpool
from goperation.utils import safe_func_wrapper
from goperation.manager import common as manager_common
from goperation.manager.utils import resultutils
from goperation.manager.utils import targetutils
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

    SCHEMA = {
        'type': 'object',
        'required': ['address', 'size', 'md5', 'crc32'],
        'properties': {
            'uuid': {'type': 'string', 'format': 'uuid'},
            'crc32': {'type': 'string',
                      'pattern': '^[0-9]+?$'},
            'md5': {'type': 'string', 'format': 'md5'},
            "downloader": {'type': 'string'},
            "adapter_args": {'type': 'array'},
            "address": {'type': 'string'},
            "ext": {'oneOf': [{'type': 'string'}, {'type': 'null'}]},
            "size": {'type': 'integer'},
            "desc": {'type': 'string'},
            "status": {'type': 'string', 'enum': manager_common.DOWNFILESTATUS},
            "uploadtime": {'type': 'string', 'format': 'date-time'},
        },
    }


    def index(self, req):
        session = get_session(readonly=True)
        query = model_query(session, DownFile)
        return resultutils.results(result='list file success',
                                   data=[downfile.to_dict() for downfile in query.all()])

    def create(self, req, body):
        jsonutils.schema_validate(body, FileReuest.SCHEMA)
        address = body.pop('address')
        size = body.pop('size')
        md5 = body.pop('md5')
        crc32 = body.pop('crc32')
        ext = body.get('ext')
        status = body.get('status', manager_common.DOWNFILE_FILEOK)
        if not ext:
            ext = address.split('.')[-1]
        session = get_session()
        downfile = DownFile(uuid=body.get('uuid') or uuidutils.generate_uuid(),
                            md5=md5,
                            crc32=crc32,
                            downloader=body.get('downloader', 'http'),
                            adapter_args=body.get('adapter_args'),
                            address=address,
                            ext=ext,
                            size=size,
                            status=status,
                            desc=body.get('desc'),
                            uploadtime=body.get('uploadtime', timeutils.utcnow())
                            )
        session.add(downfile)
        session.flush()
        return resultutils.results(result='Add file success', data=[dict(uuid=downfile.uuid,
                                                                         md5=downfile.md5,
                                                                         crc32=downfile.crc32,
                                                                         size=downfile.size,
                                                                         uploadtime=downfile.uploadtime,
                                                                         downloader=downfile.downloader)])

    def show(self, req, file_id):
        session = get_session(readonly=True)
        query = model_query(session, DownFile)
        if attributes.is_uuid_like(file_id):
            query = query.filter_by(uuid=file_id)
        elif attributes.is_md5_like(file_id):
            query = query.filter_by(md5=file_id)
        elif file_id.isdigit():
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
                     'uploadtime': str(downfile.uploadtime),
                     'marks': {'uuid': downfile.uuid,
                               'md5': downfile.md5,
                               'crc32': downfile.crc32}}
        if downfile.adapter_args:
            file_info.setdefault('adapter_args', jsonutils.dumps_as_bytes(downfile.adapter_args))
        if downfile.desc:
            file_info.setdefault('desc', downfile.desc)
        resultcode = manager_common.RESULT_SUCCESS
        if downfile.status != manager_common.DOWNFILE_FILEOK:
            resultcode = manager_common.RESULT_ERROR
        return resultutils.results(result='Get file success', resultcode=resultcode,
                                   data=[file_info, ])

    def delete(self, req, file_id, body=None):
        session = get_session()
        query = model_query(session, DownFile)
        if attributes.is_uuid_like(file_id):
            query = query.filter_by(uuid=file_id)
        elif attributes.is_md5_like(file_id):
            query = query.filter_by(md5=file_id)
        elif file_id.isdigit():
            query = query.filter_by(crc32=file_id)
        else:
            raise InvalidArgument('File id not uuid or md5 or crc32')
        with session.begin():
            downfile = query.one_or_none()
            if not downfile:
                return resultutils.results(result='Delete file do nothing, not found')
            query.delete()

        return resultutils.results(result='Delete file success', data=[dict(uuid=downfile.uuid,
                                                                            md5=downfile.md5,
                                                                            crc32=downfile.crc32,
                                                                            size=downfile.size,
                                                                            address=downfile.address,
                                                                            uploadtime=downfile.uploadtime,
                                                                            downloader=downfile.downloader)])

    def update(self, req, file_id, body=None):
        body = body or {}
        status = body.pop('status', None)
        if status not in manager_common.DOWNFILESTATUS:
            raise InvalidArgument('status value error')
        session = get_session()
        query = model_query(session, DownFile)
        if attributes.is_uuid_like(file_id):
            query = query.filter_by(uuid=file_id)
        elif attributes.is_md5_like(file_id):
            query = query.filter_by(md5=file_id)
        elif file_id.isdigit():
            query = query.filter_by(crc32=file_id)
        else:
            raise InvalidArgument('File id not uuid or md5 or crc32')
        with session.begin():
            downfile = query.one()
            query.update({'status': status})
        return resultutils.results(result='Update file success', data=[dict(uuid=downfile.uuid,
                                                                            md5=downfile.md5,
                                                                            crc32=downfile.crc32,
                                                                            size=downfile.size,
                                                                            status=downfile.status,
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
