import re

regx_endpoint = re.compile('^[a-z0-9]+$', re.IGNORECASE)

MAX_ENDPOINT_NAME_SIZE = 64
MAX_HOST_NAME_SIZE = 128