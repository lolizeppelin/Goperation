import functools
import webob.exc

from sqlalchemy.sql import and_

from simpleutil.common.exceptions import InvalidArgument
from simpleutil.common.exceptions import InvalidInput
from simpleutil.log import log as logging
from simpleutil.utils import jsonutils
from simpleutil.utils import uuidutils
from simpleutil.utils import timeutils
from simpleutil.utils import timeutils
from simpleutil.utils.attributes import validators

from simpleservice.ormdb.api import model_query
from simpleservice.rpc.exceptions import AMQPDestinationNotFound
from simpleservice.rpc.exceptions import MessagingTimeout
from simpleservice.rpc.exceptions import NoSuchMethod

from goperation.manager import common as manager_common
from goperation.manager import utils
from goperation.manager import resultutils
from goperation.manager import targetutils
from goperation.manager.api import get_client
from goperation.manager.api import get_redis
from goperation.manager.api import get_cache
from goperation.manager.api import get_global
from goperation.manager.api import get_session
from goperation.manager.api import rpcfinishtime
from goperation.manager.models import Agent
from goperation.manager.models import AgentEndpoint
from goperation.manager.models import AllocatedPort
from goperation.manager.models import DownFile
from goperation.manager.wsgi.contorller import BaseContorller
from goperation.manager.exceptions import CacheStoneError
from goperation.manager.wsgi.exceptions import RpcPrepareError
from goperation.manager.wsgi.exceptions import RpcResultError


LOG = logging.getLogger(__name__)

FAULT_MAP = {InvalidArgument: webob.exc.HTTPClientError,
             NoSuchMethod: webob.exc.HTTPNotImplemented,
             AMQPDestinationNotFound: webob.exc.HTTPServiceUnavailable,
             MessagingTimeout: webob.exc.HTTPServiceUnavailable,
             RpcResultError: webob.exc.HTTPInternalServerError,
             CacheStoneError: webob.exc.HTTPInternalServerError,
             RpcPrepareError: webob.exc.HTTPInternalServerError,
             }


class FileReuest(BaseContorller):


    def index(self, req, body):
        session = get_session(readonly=True)
        query = model_query(session, DownFile)
        return resultutils.results(result='list file success',
                                   data=[downfile.to_dict() for downfile in query.all()])

    def show(self, req, file_id, body):
        session = get_session(readonly=True)
        query = model_query(session, DownFile)
        if uuidutils.is_uuid_like(file_id):
            query = query.filter(uuid=file_id)
        elif jsonutils.is_md5_like(file_id):
            query = query.filter(md5=file_id)
        elif jsonutils.is_crc32_like(file_id):
            query = query.filter(crc32=file_id)
        else:
            raise InvalidArgument('File id not uuid or md5 or crc32')
        downfile = query.one()
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
        return file_info

    def create(self, req, body):
        address = body.get('address')
        if not address:
            raise InvalidArgument('Add file miss address')
        ext = body.get('ext')
        if not ext:
            ext = address.split('.')[-1]
        downfile = DownFile(md5 = body.get('md5'),
                            crc32 = body.get('crc32'),
                            downloader=body.get('downloader', 'http'),
                            adapter_args=body.get('adapter_args'),
                            address=address,
                            ext=ext,
                            size=body.get('size'),
                            desc=body.get('desc'),
                            uploadtime=body.get('uploadtime', timeutils.utcnow())
                            )
        return resultutils.results(result='Add file success', data=[downfile.to_dict()])


    def delete(self, req, file_id, body):
        session = get_session()
        query = model_query(session, DownFile)
        if uuidutils.is_uuid_like(file_id):
            query = query.filter(uuid=file_id)
        elif jsonutils.is_md5_like(file_id):
            query = query.filter(md5=file_id)
        elif jsonutils.is_crc32_like(file_id):
            query = query.filter(crc32=file_id)
        else:
            raise InvalidArgument('File id not uuid or md5 or crc32')
        with session.begin():
            downfile = query.one()
            count = query.delete()
        if count:
            return resultutils.results(result='Delete file success', data=[downfile.to_dict()])
        return resultutils.results(resultcode=manager_common.RESULT_ERROR,
                                   result='Delete file success')


    @BaseContorller.AgentsIdformater
    def send(self, req, agent_id, file_id, body):
        """call by client, and asyncrequest
        send file to agents
        """
        raise NotImplementedError

    @BaseContorller.AgentIdformater
    def list(self, req, agent_id, body):
        """call by client, and asyncrequest
        send file to agents
        """
        raise NotImplementedError

    @BaseContorller.AgentIdformater
    def clean(self, req, agent_id, file_id, body):
        """call by client, and asyncrequest
        send file to agents
        """
        raise NotImplementedError