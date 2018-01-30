REGEX = '^(all|[1-9]\d*?|[1-9]\d*?-[1-9]\d*?)$'

import re

x = re.compile(REGEX)

match = re.search(x, '03544')

print match
if match:
    print match.groups()
