from simpleservice.common import *

ENV_REQUEST_ID = 'goperation.request_id'

RPC_CALL_TIMEOUT = 3
RPC_SEND_RETRY = 1

# agent tpye
AGENT = 'agent'
APPLICATION = 'application'
SCHEDULER = 'scheduler'
# status of agent
ACTIVE = 1
UNACTIVE = 0
DELETED = -1
# default time of agent status key in redis
ONLINE_EXIST_TIME = 600

MAX_REQUEST_RESULT = 256
MAX_DETAIL_RESULT = 20000
MAX_AGENT_RESULT = 1024

MAX_PORTS_RANGE_SIZE = 1024

MAX_ROW_PER_REQUEST = 100
ROW_PER_PAGE = MAX_ROW_PER_REQUEST/10

# status of agent respone
STATUS_UNKNOWN = -1
STATUS_OVER_TIME = 0
STATUS_ALL_SUCCESS = 2
STATUS_NOT_ALL_SUCCESS = 1

RESULT_ERROR_EXT = RESULT_ERROR + 1
