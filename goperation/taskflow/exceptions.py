class TaskExecuteError(Exception):
    """"""


class TaskRevertError(Exception):
    """"""


class DatabaseExecuteError(TaskExecuteError):
    """"""


class DatabaseRevertError(TaskRevertError):
    """"""
