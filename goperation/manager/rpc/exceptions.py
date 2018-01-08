class RpcCtxtException(Exception):

    def __init__(self, result=None):
        self.result = result


class RpcBaseException(Exception):

    def __init__(self, endpoint, entity, reason):
        message = 'Rpc target %s:%s %s' % (endpoint,
                                           entity if isinstance(entity, (int, long)) else str(entity),
                                           reason)
        super(Exception, self).__init__(message)


class RpcTargetLockException(RpcBaseException):

    def __init__(self, endpoint, entity, reason='allocate lock timeout'):
        super(RpcTargetLockException, self).__init__(endpoint, entity, reason)


class RpcEntityError(RpcBaseException):

    def __init__(self, endpoint, entity, reason):
        reason='create entity %s' % reason
        super(RpcEntityError, self).__init__(endpoint, entity, reason)
