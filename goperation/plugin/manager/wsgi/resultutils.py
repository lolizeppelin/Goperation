from simpleutil.utils import jsonutils


def results(total=0,
            pagenum=0,
            msg=None,
            data=None,):
    ret_dict = {'total': 0,
                'pagenum': 0,
                'msg': '',
                'data': []}
    if total:
        ret_dict['total'] = total
    if pagenum:
        ret_dict['pagenum'] = pagenum
    if msg:
        ret_dict['msg'] = msg
    if data:
        ret_dict['data'] = data
    if not isinstance(ret_dict['data'], list):
        raise TypeError('results data type error')
    return ret_dict


def request(_request, agents=False, details=False):
    ret_dict = {'request_id': _request.request_id,
                'request_time': _request.request_time,
                'finishtime': _request.finishtime,
                'deadline': _request.deadline,
                'async_checker': _request.async_checker,
                'status': _request.status,
                'result': _request.result,
                'respones': []
                }
    if agents:
        for agent_data in _request.respones:
            ret_dict['respones'].append(agent(agent_data),
                                        details=details)
    return ret_dict


def agent(_agent, details=False):
    ret_dict = {'agent_id': _agent.agent_id,
                'server_time': _agent.server_time,
                'agent_time': _agent.agent_time,
                'result': _agent.result,
                'status': _agent.status,
                'details': []}
    if details:
        for detail_data in _agent.details:
            ret_dict['details'].append(dict(detail_id=detail_data.detail_id,
                                            result=jsonutils.loads(detail_data.result)
                                            )
                                       )
    return ret_dict
