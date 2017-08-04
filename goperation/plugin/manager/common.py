from simpleservice.common import *

ENV_REQUEST_ID = 'goperation.request_id'

RPC_CALL_TIMEOUT = 3
RPC_SEND_RETRY = 1

# agent tpye
AGENT = 'agent'
APPLICATION = 'application'
SCHEDULER = 'scheduler'


# -----------status of agent--------------
ACTIVE = 1
UNACTIVE = 0
INITIALIZING = -1
SOFTBUSY = -9
HARDBUSY = -10
DELETED = -127
# per delete status can not be recode into database
# agent set status as PERDELETE when get a rpc cast of delete_agent_precommit
PERDELETE = -128
# -----------status of agent--------------


# ------status of async request-----------
FINISH = 1
UNFINISH = 0
# ------status of async request-----------

# default time of agent status key in redis
ONLINE_EXIST_TIME = 600

MAX_REQUEST_RESULT = 256
MAX_DETAIL_RESULT = 20000
MAX_AGENT_RESULT = 1024

MAX_PORTS_RANGE_SIZE = 1024

MAX_ROW_PER_REQUEST = 100
ROW_PER_PAGE = MAX_ROW_PER_REQUEST/10


RESULT_NOT_ALL_SUCCESS = RESULT_SUCCESS + 1