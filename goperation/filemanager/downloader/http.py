import time
import requests
from contextlib import closing

from goperation.filemanager import exceptions
from goperation.filemanager.downloader.base import DonwerAdapter

CHUNK = 8192

class HttpAdapter(DonwerAdapter):

    def __init__(self, headers=None, timeout=5):
        # socket timeout
        self.headers = headers
        self.timeout = timeout

    def download(self, address, dst, timeout):
        if timeout:
            timeout = time.time() + timeout
        else:
            timeout = timeout.time() + 18000
        with closing(requests.get(address,
                                  stream=True, headers=self.headers,
                                  timeout=self.timeout)) as response:

            with open(dst, 'wb') as f:
                for buf in response.iter_content(CHUNK):
                    if time.time() > timeout:
                        raise exceptions.DownLoadTimeout('Download http file overtime')
                    f.write(buf)
