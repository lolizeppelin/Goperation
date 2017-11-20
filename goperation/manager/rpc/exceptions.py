class RpcCtxtException(Exception):

    def __init__(self, result=None):
        self.result = result


class RpcBaseException(Exception):

    def __init__(self, endpoint, entity, reason):
        self.message = 'Rpc target %s:%d %s' % (endpoint, entity, reason)


class RpcTargetLockException(RpcBaseException):

    def __init__(self, endpoint, entity, reason='allocate lock timeout'):
        super(RpcCtxtException).__init__(endpoint, entity, reason)


class RpcEntityError(RpcBaseException):

    def __init__(self, endpoint, entity, reason):
        super(RpcCtxtException).__init__(endpoint, entity, 'create entity %s' % reason)
