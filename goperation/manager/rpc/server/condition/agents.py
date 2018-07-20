# -*- coding:utf-8 -*-
from sqlalchemy.orm import joinedload

from simpleservice.ormdb.api import model_query

from goperation.manager.api import get_session
from goperation.manager.utils import resultutils
from goperation.manager.rpc import exceptions
from goperation.manager.rpc.server import condition
from goperation.manager.models import AsyncRequest

from goperation.manager.rpc.server.utils import OPERATIORS


class Condition(condition.BaseCondition):

    def pre_run(self, asyncrequest, wait_agents):
        """Agents condition has no pre check"""

    def after_run(self, asyncrequest, wait_agents):
        kwargs = self.kwargs
        if not kwargs:
            return

        counter = kwargs.get('counter')
        if not counter:
            raise exceptions.RpcServerCtxtException('No counter found for agent')

        counter = OPERATIORS[counter]
        count = kwargs.get('count')
        if not counter(len(wait_agents), count):
            raise exceptions.RpcServerCtxtException('Agent count not match')

    def post_run(self, asyncrequest, no_response_agents):
        kwargs = self.kwargs
        if not kwargs:
            return

        all = kwargs.get('all', True)
        if all and no_response_agents:
            raise exceptions.RpcServerCtxtException('Check fail, same agent not respone')

        operator = kwargs.get('operator')
        operator = OPERATIORS[operator]
        value = kwargs.get('value')

        counter = kwargs.get('counter')
        if counter:
            counter = OPERATIORS[counter]
            count = kwargs.get('count')
        elif not all:
            raise exceptions.RpcServerCtxtException('No counter found when all is False')

        query = model_query(get_session(readonly=True), AsyncRequest,
                            filter=AsyncRequest.request_id == asyncrequest.request_id)
        joins = joinedload(AsyncRequest.respones, innerjoin=False)
        query = query.options(joins)
        asyncrequest = query.one()
        results = resultutils.async_request(asyncrequest, agents=True, details=False)
        respones = results.get('respones')

        _count = 0
        for respone in respones:
            if operator(respone.get('resultcode'), value):
                _count += 1
            elif all:
                raise exceptions.RpcServerCtxtException('Check fail, agent %d resultcode not match' %
                                                        respone.get('agent_id'))
        if counter and not counter(_count, count):
            raise exceptions.RpcServerCtxtException('Check fail, agents count not match')
