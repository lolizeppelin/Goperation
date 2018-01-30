import time
import sys
from simpleutil.utils import table
from simpleutil.utils import timeutils

from simpleservice.plugin.exceptions import HttpRequestError
from simpleservice.plugin.exceptions import AfterRequestError


def prepare_results(func, *args, **kwargs):
    try:
        r = func(*args, **kwargs)
    except AfterRequestError as e:
        print('\033[1;31;40m')
        print 'Request Fail, http code %d, err msg %s' % (e.code, e.message)
        print 'Resoin is %s' % e.resone
        print('\033[0m')
        sys.exit(1)
    except HttpRequestError as e:
        print('\033[1;31;40m')
        print 'Request Fail, http request not send: %s' % e.message
        print('\033[0m')
        sys.exit(1)
    if r is None:
        raise ValueError('Resulst is None')
    return r.get('resultcode'), r.get('result'), r.get('data')


def p_asyncrequest(client, request_id, details=False):
    code, result, data = prepare_results(client.async_show,
                                         request_id=request_id,
                                         body=dict(details=details))
    heads = ['request_id', 'code', 'reqtime', 'finishtime', 'deadline', 'expire', 'status', 'result']
    heads_agents = ['agent', 'code', 'sendtime', 'recvtime', 'result']
    heads_details = ['id', 'code', 'result']
    if not data:
        print 'No agent respones found for %s' % request_id
        print 'resultcode: %d result: %s' % (code, result)
    for r in data:
        tb = table.PleasantTable(ident=0, columns=heads, counter=False)
        tb.add_row([r.get('request_id'), r.get('resultcode'),
                    timeutils.unix_to_iso(r.get('request_time')),
                    timeutils.unix_to_iso(r.get('finishtime')),
                    timeutils.unix_to_iso(r.get('deadline')),
                    r.get('status'), r.get('expire'), r.get('result')
                    ])
        print tb.pformat()
        for rr in r.get('respones'):
            tb = table.PleasantTable(ident=15, columns=heads_agents, counter=False)
            tb.add_row([rr.get('agent_id'), rr.get('resultcode'),
                        timeutils.unix_to_iso(rr.get('agent_time')),
                        timeutils.unix_to_iso(rr.get('server_time')),
                        rr.get('result')
                        ])
            print tb.pformat()
            if details:
                details = rr.get('details')
                tb = table.PleasantTable(ident=30, columns=heads_details)
                if details:
                    for rrr in details:
                        tb.add_row([rrr.get('detail_id'), rrr.get('resultcode'), rrr.get('result')])
                print tb.pformat()


def is_finished(client, request_id):
    code, result, data = prepare_results(client.async_show,
                                         request_id=request_id,
                                         body=dict(details=False, agents=False))
    if code:
        raise ValueError('Fail, code %d, result %s' % (code, result))
    asyncrequest = data[0]
    if asyncrequest.get('status'):
        return True
    else:
        return False


def wait_finish(client, asyncrequest):
    now = int(time.time())
    request_id = asyncrequest.get('request_id')
    finishtime = asyncrequest.get('finishtime')
    deadline = asyncrequest.get('deadline') + 3
    time.sleep(3)
    sleep = now - finishtime
    if sleep >= 3:
        time.sleep(3)
        if is_finished(client, request_id):
            return True
    time.sleep(sleep - 3)
    while int(time.time()) < deadline:
        if not is_finished(client, request_id):
            time.sleep(1)
        else:
            return True
    return False
