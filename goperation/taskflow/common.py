class NOT_EXECUTED:
    def __repr__(self):
        return 'not executed'

class REVERTED:
    def __repr__(self):
        return 'reverted'

class REVERT_FAIL:
    def __repr__(self):
        return 'revert fail'

class EXECUTE_SUCCESS:
    def __repr__(self):
        return 'execute success'

class EXECUTE_FAIL:
    def __repr__(self):
        return 'execute fail'


NOT_EXECUTED = NOT_EXECUTED()
REVERTED = REVERTED()
REVERT_FAIL = REVERT_FAIL()
EXECUTE_SUCCESS = EXECUTE_SUCCESS()
EXECUTE_FAIL = EXECUTE_FAIL()