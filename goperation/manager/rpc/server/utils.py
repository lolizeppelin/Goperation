import re
import operator
from simpleutil.common.exceptions import InvalidArgument

OPERATIORS = {'<': operator.lt,
              '>': operator.gt,
              '=': operator.eq,
              '!=': operator.ne,
              '<=': operator.le,
              '>=': operator.ge,
              }

regx = re.compile('([a-zA-Z]*?[a-zA-Z0-9._]*?[a-zA-Z0-1])?([\<\>\!\=]+)?([0-9a-zA-Z._]+)?$')


def include(includes):
    _includes = {}

    for include in includes:
        match = re.match(regx, include)
        if not match:
            raise InvalidArgument('Include string match fail')
        key = OPERATIORS[match.group(0)]
        _operator = OPERATIORS[match.group(1)]
        value = OPERATIORS[match.group(2)]
        if value.isdigit():
            value = int(value)
        try:
            _includes[key].append((_operator, value))
        except KeyError:
            _includes[key] = [(_operator, value)]

    return _includes
