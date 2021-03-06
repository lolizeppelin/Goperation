import six
import abc
from sqlalchemy.orm.attributes import InstrumentedAttribute

from simpleutil.utils import jsonutils
from simpleutil.utils import timeutils
from simpleutil.common.exceptions import InvalidArgument

from simpleservice.ormdb.api import model_query
from simpleservice.ormdb.api import model_count_with_key
from simpleservice.plugin.httpclient import results

from goperation.manager.api import get_cache
from goperation.manager.utils import targetutils
from goperation.manager import common as manager_common


def bulk_results(session,
                 model,
                 columns,
                 counter=None,
                 order=None, desc=None,
                 filter=None,
                 option=None,
                 page_num=0,
                 limit=None):
    query = model_query(session, model, filter=filter)
    if option:
        query = query.options(option)

    def validator(_column):
        if isinstance(_column, basestring):
            if hasattr(model, _column) and isinstance(getattr(_column, _column), InstrumentedAttribute):
                intance = model.__dict__[_column]
                name = _column
            else:
                raise InvalidArgument('Can not find column %s in %s' % (_column, model.__tablename__))
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
    # check page number
    if page_num:
        # count row number
        all_rows_num = model_count_with_key(session,
                                            counter,
                                            filter=filter)
        if page_num*manager_common.ROW_PER_PAGE >= all_rows_num:
            raise InvalidArgument('Page number over size or no data exist')
        query.seek(page_num*manager_common.ROW_PER_PAGE)
    limit = limit or manager_common.MAX_ROW_PER_REQUEST
    query = query.limit(limit)
    row_list = []
    for result in query:
        column = dict()
        for column_name in column_name_list:
            column[column_name] = getattr(result, column_name)
        row_list.append(column)
    result = 'Get results success'
    if len(row_list) == 0:
        result = 'No result found'
    ret_dict = results(total=0,
                       pagenum=page_num,
                       data=row_list, result=result)
    return ret_dict


def async_request(_request, agents=False, details=False):
    """this function just for route asynrequest show"""
    req_dict = {'request_id': _request.request_id,
                'request_time': _request.request_time,
                'finishtime': _request.finishtime,
                'deadline': _request.deadline,
                'status': _request.status,
                'expire': _request.expire,
                'resultcode': _request.resultcode,
                'result': _request.result,
                'respones': []
                }
    # ret_dict = results(data=[req_dict, ], result='Get async request data finish')
    if _request.expire:
        req_dict['result'] += ',Data in cache,May miss some respone'
    if agents:
        if _request.expire:
            _cache = get_cache()
            key_pattern = targetutils.async_request_pattern(_request.request_id)
            respone_keys = _cache.keys(key_pattern)
            if respone_keys:
                agent_respones = _cache.mget(*respone_keys)
                if agent_respones:
                    for agent_respone in agent_respones:
                        if agent_respone:
                            try:
                                agent_respone_data = jsonutils.loads_as_bytes(agent_respone)
                            except (TypeError, ValueError):
                                continue
                            if not details:
                                agent_respone_data.pop('details', None)
                            req_dict['respones'].append(agent_respone_data)
        else:
            for agent_data in _request.respones:
                req_dict['respones'].append(agent(agent_data, details=details))
    return req_dict


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
                # 'result': jsonutils.loads_as_bytes(_detail.result)
                'result': _detail.result
                }
    return ret_dict


@six.add_metaclass(abc.ABCMeta)
class BaseRpcResult(object):

    def __init__(self, resultcode=0, result=None):
        self.resultcode = resultcode
        self.result = result

    @abc.abstractmethod
    def to_dict(self):
        """change intacne to dict"""


class ServerRpcResult(BaseRpcResult):
    """"""

    def __init__(self, host, resultcode=0, result=None, ):
        self.host = host
        super(ServerRpcResult, self).__init__(resultcode, result)

    def to_dict(self):
        ret_dict = {'resultcode': self.resultcode,
                    'host': self.host,
                    'result': self.result if self.result else 'unkonwn result'}
        return ret_dict


class AgentRpcResult(BaseRpcResult):

    def __init__(self, agent_id, ctxt=None,
                 resultcode=0, result=None, details=None):
        self.agent_id = agent_id
        self.details = details
        self.agent_time = int(timeutils.realnow())
        self.expire = ctxt.get('expire', 0)
        super(AgentRpcResult, self).__init__(resultcode, result)

    def to_dict(self):
        ret_dict = {'agent_id': self.agent_id,
                    'resultcode': self.resultcode,
                    'result': self.result if self.result else 'unkonwn result',
                    'agent_time': self.agent_time,
                    'expire': self.expire
                    }
        if self.details:
            ret_dict['details'] = self.details
        return ret_dict


class UriResult(BaseRpcResult):
    def __init__(self, resultcode=0, result=None, uri=None):
        self.uri = uri
        super(UriResult, self).__init__(resultcode, result)

    def to_dict(self):
        ret_dict = {'resultcode': self.resultcode,
                    'uri': self.uri,
                    'result': self.result if self.result else 'unkonwn result'}
        return ret_dict


class DirResult(BaseRpcResult):
    def __init__(self, resultcode=0, result=None, dirs=None, files=None):
        self.dirs = dirs or []
        self.files = files or []
        super(DirResult, self).__init__(resultcode, result)

    def to_dict(self):
        ret_dict = {'resultcode': self.resultcode,
                    'dirs': self.dirs,
                    'files': self.files,
                    'result': self.result if self.result else 'unkonwn result'}
        return ret_dict
