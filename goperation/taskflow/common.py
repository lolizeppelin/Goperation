class NOT_EXECUTED:
    def __repr__(self):
        return 'not executed'

class REVERTED:
    def __repr__(self):
        return 'reverted'

class EXECUTE_SUCCESS:
    def __repr__(self):
        return 'execute success'

class EXECUTE_FAIL:
    def __repr__(self):
        return 'execute fail'


NOT_EXECUTED = NOT_EXECUTED()
REVERTED = REVERTED()
EXECUTE_SUCCESS = EXECUTE_SUCCESS()
EXECUTE_FAIL = EXECUTE_FAIL()