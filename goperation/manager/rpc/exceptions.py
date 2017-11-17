class RpcCtxtException(Exception):

    def __init__(self, result=None):
        self.result = result


class RpcCtxtTargetLockException(Exception):

    def __init__(self, endpoint, entity, reason='allocate lock timeout'):
        self.message = 'Rpc target %s:%d %s' % (endpoint, entity, reason)