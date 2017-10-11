import datetime
import sqlalchemy as sa
from sqlalchemy.ext import declarative
from sqlalchemy import DATETIME
from sqlalchemy import VARCHAR
from sqlalchemy import CHAR
from sqlalchemy import BIGINT

from simpleservice.ormdb.models import TableBase

UUID_LENGTH = 36
MD5_LENGTH = 32
CRC32_LENGTH = 32
DETAIL_LENGTH = 512
ADDRESS_LENGTH = 512

FileManagerTables = declarative.declarative_base(cls=TableBase)

class FileDetail(FileManagerTables):
    uuid = sa.Column(CHAR(UUID_LENGTH), primary_key=True, nullable=False)
    size = sa.Column(BIGINT, nullable=False)
    crc32 = sa.Column(VARCHAR(CRC32_LENGTH), nullable=False)
    md5 = sa.Column(CHAR(MD5_LENGTH), unique=True, nullable=False)
    ext = sa.Column(VARCHAR(32), nullable=False)
    detail = sa.Column(VARCHAR(DETAIL_LENGTH), default='unkown file', nullable=False)
    address = sa.Column(VARCHAR(ADDRESS_LENGTH), default=None, nullable=True)
    uploadtime = sa.Column(DATETIME, default=datetime.datetime.now, nullable=True)
