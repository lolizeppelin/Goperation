class RpcResultError(Exception):
    """rpc call result error"""


class RpcPrepareError(Exception):
    """rpc msg prepare error"""


class AsyncRpcPrepareError(RpcPrepareError):
    """async rpc msg prepare error"""


class AgentMetadataMiss(Exception):
    """Agent meta data miss"""
