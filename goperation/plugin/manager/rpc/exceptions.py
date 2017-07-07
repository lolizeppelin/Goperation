from simpleservice.rpc.driver.exceptions import MessagingException


class RPCResultError(MessagingException):
    """rpc call error"""