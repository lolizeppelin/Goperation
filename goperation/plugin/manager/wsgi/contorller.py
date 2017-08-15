from simpleutil.utils import timeutils
from simpleutil.utils import uuidutils

from simpleutil.common.exceptions import InvalidArgument

from goperation.plugin.manager.models import AsyncRequest
from goperation.plugin.manager import common as manager_common
from goperation.plugin.manager.api import rpcdeadline


MAX_ROW_PER_REQUEST = 100


class BaseContorller():

    @staticmethod
    def request_id_check(request_id):
        if not uuidutils.is_uuid_like(request_id):
            raise InvalidArgument('Request id is not uuid like')

    @staticmethod
    def create_asyncrequest(req, body):
        """async request use this to create a new request
        argv in body
        request_time:  unix time in seconds that client send async request
        finishtime:  unix time in seconds that work shoud be finished after this time
        deadline:  unix time in seconds that work will igonre after this time
        persist: 0 or 1, if zero, respone will store into redis else store into database
        """
        request_time = int(timeutils.realnow())
        persist = body.get('persist', 1)
        if persist not in (0, 1):
            raise InvalidArgument('Async argv persist not in 0, 1')
        try:
            client_request_time = int(body.get('request_time'))
        except KeyError:
            raise InvalidArgument('Async request need argument request_time')
        except TypeError:
            raise InvalidArgument('request_time is not int of time or no request_time found')
        offset_time = request_time - client_request_time
        if abs(offset_time) > 5:
            raise InvalidArgument('The diff time between send and receive is %d' % offset_time)
        finishtime = body.get('finishtime', None)
        if finishtime:
            finishtime = int(finishtime) + offset_time
        else:
            finishtime = request_time + 4
        if finishtime - request_time < 3:
            raise InvalidArgument('Job can not be finished in 3 second')
        deadline = body.get('deadline', None)
        if deadline:
            deadline = int(deadline) + offset_time - 1
        else:
            deadline = rpcdeadline(finishtime)
        if deadline - finishtime < 3:
            raise InvalidArgument('Job deadline must at least 3 second after finishtime')
        request_id = uuidutils.generate_uuid()
        req.environ[manager_common.ENV_REQUEST_ID] = request_id
        new_request = AsyncRequest(request_id=request_id,
                                   request_time=request_time,
                                   finishtime=finishtime,
                                   deadline=deadline,
                                   persist=persist)
        return new_request
