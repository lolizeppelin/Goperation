from simpleutil.utils.timeutils import realnow

from simpleservice.rpc.exceptions import MessageNotForMe
from simpleservice.rpc.result import BaseRpcResult

from goperation import threadpool
from goperation.manager import common as manager_common
from goperation.manager.rpc import exceptions


class CheckRpcCtxt(object):

    def __init__(self, func=None):
        self.func = func
        self.manager = None

    def __get__(self, instance, owner):
        self.func = self.func.__get__(instance, owner)
        self.manager = instance.manager if hasattr(instance, 'manager') else instance
        return self

    def __call__(self, *args, **kwargs):
        raise NotImplementedError

    def check_status(self, ctxt):
        if not self.manager.is_active:
            result = BaseRpcResult(self.manager.agent_id, ctxt,
                                   resultcode=manager_common.RESULT_ERROR,
                                   result='Agent status is not active')
            raise exceptions.RpcCtxtException(result=result)

    def check_pool(self, ctxt):
        if threadpool.pool.free() < (threadpool.pool.size/10) + 2:
            result = BaseRpcResult(self.manager.agent_id, ctxt,
                                   resultcode=manager_common.RESULT_ERROR,
                                   result='Agent public thread pool is busy')
            raise exceptions.RpcCtxtException(result=result)


class CheckManagerRpcCtxt(CheckRpcCtxt):
    """Rpc call need this to check ctxt
    else you shoud check finishtime on ctxt
    and chekc status of Manager
    """

    def __call__(self, *args, **kwargs):
        # see simpleservice.rpc.driver.dispatcher.py
        # for dispatch call_endpoint endpoint, method, ctxt, **args
        ctxt = args[0] if len(args) == 1 else args[2]
        finishtime = ctxt.get('finishtime', None)
        agents = ctxt.get('agents', None)
        try:
            if agents and self.manager.agent_id not in agents:
                # rpc not for this agent
                raise MessageNotForMe
            if finishtime and int(realnow()) >= finishtime:
                msg = 'Rpc receive time over finishtime'
                result = BaseRpcResult(self.manager.agent_id, ctxt,
                                       resultcode=manager_common.RESULT_OVER_FINISHTIME, result=msg)
                raise exceptions.RpcCtxtException(result)
            file_info = ctxt.pop('file', None)
            if file_info:
                target_file = self.manager.files.find_file(file_info)
                if not target_file:
                    result = BaseRpcResult(self.manager.agent_id, ctxt,
                                           resultcode=manager_common.RESULT_ERROR,
                                           result='Could not find target file')
                    raise exceptions.RpcCtxtException(result)
                # change file info to  object
                ctxt.setdefault('file', target_file)
            # check success run rpc function
            result = self.func(*args, **kwargs)
        except MessageNotForMe:
            raise
        except exceptions.RpcCtxtException as e:
            result = e.result
        except Exception as e:
            # cache rpc function Exception so we can
            # respone fail infomation to wsgi server for rpc cast
            # witch ctxt include key request_id
            result = e
        # get a request_id means the asyncrequest need to post data to gcenter
        # TODO this part should in AMQPIncomingMessage.relay
        request_id = ctxt.get('request_id', None)
        if request_id:
            if isinstance(result, BaseRpcResult):
                http_result = result.to_dict()
            elif isinstance(result, Exception):
                # TODO shoul get more details for exception like
                # simpleservic.rpc.driver.common.serialize_remote_exception dose
                msg = 'Call rpc function catch %s' % result.__class__.__name__
                # exc_info = sys.exc_info()
                # del exc_info
                http_result = BaseRpcResult(self.manager.agent_id, ctxt,
                                            resultcode=manager_common.RESULT_ERROR,
                                            result=msg)
            elif isinstance(result, dict):
                http_result = result
            else:
                http_result = BaseRpcResult(self.manager.agent_id, ctxt,
                                            resultcode=manager_common.RESULT_ERROR,
                                            result='Rpc result value type error: %s' % str(result))
            self.manager.client.async_resopne(request_id, http_result)
        # raise Exception to dispatch
        if isinstance(result, Exception):
            raise result
        return result


class CheckEndpointRpcCtxt(CheckRpcCtxt):

    def __call__(self, *args, **kwargs):
        ctxt = args[2]
        endpoint = args[0]
        self.check_status(ctxt)
        self.check_pool(ctxt)
        # destination entitys count
        # if not set, means all entitys of endpoint in this agent
        entitys = ctxt.get('entitys', len(endpoint.entitys))
        if not isinstance(entitys, (int, long)):
            result = BaseRpcResult(self.manager.agent_id, ctxt,
                                   resultcode=manager_common.RESULT_ERROR,
                                   result='entitys value type error')
            raise exceptions.RpcCtxtException(result=result)
        if entitys:
            # check space for entitys
            target_file = ctxt.pop('file', None)
            if target_file:
                if target_file.size * entitys > self.manager.partion_left_size - 100:
                    result = BaseRpcResult(self.manager.agent_id, ctxt,
                                           resultcode=manager_common.RESULT_ERROR,
                                           result='Not enough space for %d entitys' % entitys)
                    raise exceptions.RpcCtxtException(result=result)
        return self.func(*args, **kwargs)



class CheckThreadPoolRpcCtxt(CheckRpcCtxt):

    def __call__(self, *args, **kwargs):
        ctxt = args[0]
        self.check_status(ctxt)
        self.check_pool(ctxt)
        return self.func(*args, **kwargs)

