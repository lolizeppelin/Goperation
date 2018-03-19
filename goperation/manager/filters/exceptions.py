class InvalidAuthToken(Exception):
    """Token error"""


class InvalidOriginError(Exception):
    """Exception raised when Origin is invalid."""

    def __init__(self, origin):
        self.origin = origin
        super(InvalidOriginError, self).__init__(
            'CORS request from origin \'%s\' not permitted.' % origin)
