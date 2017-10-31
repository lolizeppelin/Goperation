class AllocLockTimeout(Exception):
    """alloc GlobalLock timeout"""


class EndpointNotTheSame(Exception):
    """lock entitys find entitys endpoint not the same"""


class TargetCountUnequal(Exception):
    """lock target count not equal in database"""


class CacheStoneError(Exception):
    """cache error"""


class EndpointNotEmpty(Exception):
    """Endpoint can not be delete because still has entity"""


class AgentHostExist(Exception):
    """Agent host dulcale"""


class DeleteCountNotSame(Exception):
    """delete count not eq"""
