class RpcCtxtException(Exception):

    def __init__(self, result=None):
        self.result = result
