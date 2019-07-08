class FileManagerError(Exception):
    """"""


class NoFileFound(FileManagerError):
    """"""


class FileIsMiss(FileManagerError):
    """"""


class FileNotMatch(FileManagerError):
    """"""


class DownLoadFail(FileManagerError):
    """"""


class DownLoadTimeout(FileManagerError):
    """"""


class DownLoading(FileManagerError):
    """"""
