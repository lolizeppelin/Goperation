# -*- coding:utf-8 -*-
# -*- coding:utf-8 -*-
from sqlalchemy.orm import joinedload

from simpleservice.ormdb.api import model_query

from goperation.manager import common as manager_common
from goperation.manager.api import get_session
from goperation.manager.utils import resultutils
from goperation.manager.rpc.server import condition
from goperation.manager.models import AgentRespone
from goperation.manager.models import AsyncRequest

from goperation.manager.rpc.server.utils import OPERATIORS


class Condition(condition.BaseCondition):
    def pre_run(self, asyncrequest, wait_agents):
        """Entity condition has no pre check"""

    def after_run(self, asyncrequest, wait_agents):
        """Entity condition has no after check"""

    def post_run(self, asyncrequest, no_response_agents):
        kwargs = self.kwargs.get('post')
        if not kwargs:
            return

        all = kwargs.get('all', True)
        if all and no_response_agents:
            raise

        operator = kwargs.get('operator')
        operator = OPERATIORS[operator]
        value = kwargs.get('value')

        counter = kwargs.get('counter')
        counter = OPERATIORS[counter]
        count = kwargs.get('count')

        query = model_query(get_session(readonly=True), AsyncRequest,
                            filter=AsyncRequest.request_id == asyncrequest.request_id)
        joins = joinedload(AsyncRequest.respones, innerjoin=False)
        joins = joins.joinedload(AgentRespone.details, innerjoin=False)
        query = query.options(joins)
        asyncrequest = query.one()
        results = resultutils.async_request(asyncrequest, agents=True, details=True)
        respones = results.get('respones')

        _count = 0
        for respone in respones:
            if all and respone.get('resultcode') != manager_common.RESULT_SUCCESS:
                raise
            details = respone.get('details')
            for detail in details:
                if operator(detail.get('resultcode'), value):
                    _count += 1
                elif all:
                    raise
        if not counter(_count, count):
            raise
