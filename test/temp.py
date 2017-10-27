import re

MD5LIKE = re.compile('^[a-z0-9]{32}$')

def is_md5_like(var):
    return re.match(MD5LIKE, var) is not None

from simpleutil.utils import digestutils


var = digestutils.filemd5(r'C:\Users\loliz_000\Desktop\backup\db.sql')
print var
print digestutils.filecrc32(r'C:\Users\loliz_000\Desktop\backup\db.sql')

print is_md5_like(var)