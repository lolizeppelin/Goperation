import re

MD5LIKE = re.compile('^[a-z0-9]{32}$')

def is_md5_like(var):
    return re.match(MD5LIKE, var) is not None

from simpleutil.utils import digestutils

path = r'C:\Users\loliz_000\Desktop\2.xlsx'

var = digestutils.filemd5(path)
print var
print digestutils.filecrc32(path)

print is_md5_like(var)