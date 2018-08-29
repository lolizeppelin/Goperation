class AcceptableError(Exception):
    """error acceptable """

class UnAcceptableError(Exception):
    """error unacceptable """


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


class AgentMetadataMiss(Exception):
    """Agent meta data miss"""


class ConfigError(Exception):
    """config error"""


class TokenError(Exception):
    """"""

class FernetError(TokenError):
    """Fernet Error"""


class FernetKeysNotFound(FernetError):
    """"""

class FernetDecryptFail(FernetError):
    """"""