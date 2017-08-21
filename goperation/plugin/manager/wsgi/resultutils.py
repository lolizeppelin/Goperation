from sqlalchemy.orm.attributes import InstrumentedAttribute

from simpleutil.utils import jsonutils

from simpleutil.common.exceptions import InvalidArgument

from simpleservice.ormdb.api import model_query
from simpleservice.ormdb.api import model_count_with_key
from simpleservice.wsgi.client import results

from goperation.plugin.manager import common as manager_common


def bulk_results(session,
                 model,
                 columns,
                 counter=None,
                 order=None, desc=None,
                 filter=None,
                 page_num=0):
    query = model_query(session, model, filter=filter)

    def validator(_column):
        if isinstance(_column, basestring):
            if hasattr(model, _column) and isinstance(getattr(_column, _column), InstrumentedAttribute):
                intance = model.__dict__[_column]
                name = _column
            else:
                raise InvalidArgument('Cano not find column %s in %s' % (_column, model.__tablename__))
        elif isinstance(counter, InstrumentedAttribute):
            if counter.class_ is not model:
                raise InvalidArgument('Column %s not belong to table %s' % (counter.key, model.__tablename__))
            intance = _column
            name = _column.key
        else:
            raise InvalidArgument('Column value not basestring or intance of InstrumentedAttribute')
        return intance, name

    # formater counter
    if counter is None:
        counter = model
    counter = validator(counter)[0]

    # formater order
    if order is not None:
        order = validator(order)[0]
        if desc:
            order = order.desc()
        query = query.order_by(order)

    # format columns list to basestring
    if not columns:
        raise ValueError('Result column is None')
    column_name_list = set()
    for column in columns:
        try:
            column_name = validator(column)[1]
        except InvalidArgument as e:
            raise ValueError(e.message)
        column_name_list.add(column_name)

    # count row number
    all_rows_num = model_count_with_key(session,
                                        counter,
                                        filter=filter)
    # check page number
    if page_num:
        if not isinstance(page_num, (int, long)):
            raise InvalidArgument('Page number type error')
        if page_num*manager_common.ROW_PER_PAGE >= all_rows_num:
            raise InvalidArgument('Page number over size or no data exist')
        query.seek(page_num*manager_common.ROW_PER_PAGE)
    query = query.limit(manager_common.MAX_ROW_PER_REQUEST)
    request_list = []
    for result in query:
        data = dict()
        for column in column_name_list:
            data[column] = result.__dict__[column]
        request_list.append(data)
    result = 'Get results success'
    if len(request_list) == 0:
        result = 'No result found'
    ret_dict = results(total=all_rows_num,
                       pagenum=page_num,
                       data=request_list, result=result)
    return ret_dict


def async_request(_request, agents=False, details=False):
    """this function just for route asynrequest show"""
    res_dict = {'request_id': _request.request_id,
                'request_time': _request.request_time,
                'finishtime': _request.finishtime,
                'deadline': _request.deadline,
                'scheduler': _request.scheduler,
                'status': _request.status,
                'persist': _request.persist,
                'resultcode': _request.resultcode,
                'result': _request.result,
                'respones': []
                }
    ret_dict = results(data=[res_dict, ], result='Get async request data finish')
    if not _request.persist:
        ret_dict['result'] += ',Data in cache,May miss some respone'
    if agents:
        for agent_data in _request.respones:
            ret_dict['data'][0]['respones'].append(agent(agent_data),
                                                   details=details)
    return ret_dict


def agent(_agent, details=False):
    ret_dict = {'agent_id': _agent.agent_id,
                'server_time': _agent.server_time,
                'agent_time': _agent.agent_time,
                'resultcode': _agent.resultcode,
                'result': _agent.result,
                'details': []}
    if details:
        for detail_data in _agent.details:
            ret_dict['details'].append(detail(detail_data))
    return ret_dict


def detail(_detail):
    ret_dict = {'detail_id': _detail.detail_id,
                'resultcode': _detail.resultcode,
                'result': jsonutils.loads(_detail.result)
                }
    return ret_dict
