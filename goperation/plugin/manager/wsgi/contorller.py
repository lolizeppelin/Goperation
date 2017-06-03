from simpleutil.utils import argutils
from simpleutil.utils import timeutils
from simpleutil.utils import uuidutils

from simpleutil.common.exceptions import InvalidArgument

from goperation.plugin.manager.models import WsgiRequest
from goperation.plugin.manager import common as manager_common


MAX_ROW_PER_REQUEST = 100


class BaseContorller(argutils.IdformaterBase):

    @staticmethod
    def create_request(req, body):
        """async request use this to create a new request"""
        request_time = int(timeutils.realnow())
        try:
            client_request_time = int(body.get('request_time'))
        except KeyError:
            raise InvalidArgument('Async request need argument request_time')
        except TypeError:
            raise InvalidArgument('request_time is not int of time or no request_time found')
        diff_time = request_time - client_request_time
        if abs(diff_time) > 3000:
            raise InvalidArgument('The diff time between send and receive is %d' % diff_time)
        finishtime = body.get('finishtime', None)
        if finishtime:
            if finishtime - client_request_time < 3:
                raise InvalidArgument('Job can not be finished in 3 second')
            finishtime = int(finishtime) + diff_time
        else:
            finishtime = request_time + 4
        deadline = body.get('deadline', None)
        if deadline:
            deadline = int(deadline) + diff_time
            if deadline - finishtime < 3:
                raise InvalidArgument('Job deadline must at least 3 second after finishtime')
        else:
            deadline = finishtime + 5
        request_id = uuidutils.generate_uuid()
        req.environ[manager_common.ENV_REQUEST_ID] = request_id
        new_request = WsgiRequest(request_id=request_id,
                                  request_time=request_time,
                                  finishtime=finishtime,
                                  deadline=deadline)
        return new_request
