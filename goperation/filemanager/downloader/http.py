import time
import zlib
import hashlib
import requests
from requests.exceptions import RequestException
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
        try:
            return self._download_200(address, dst, timeout)
        except RequestException as e:
            raise exceptions.DownLoadFail('Download from %s Catch %s %s' % (address,
                                                                            e.__class__.__name__, e.message))

    def _download_200(self, address, dst, timeout):
        if timeout:
            timeout = time.time() + timeout
        else:
            timeout = time.time() + 18000
        with closing(requests.get(address, stream=True, headers=self.headers,
                                  timeout=self.timeout)) as response:
            crc = 0
            _md5sum = hashlib.md5()
            with open(dst, 'wb') as f:
                for buf in response.iter_content(CHUNK):
                    crc = zlib.crc32(buf, crc)
                    _md5sum.update(buf)
                    if time.time() > timeout:
                        raise exceptions.DownLoadTimeout('Download http file overtime')
                    f.write(buf)
        return _md5sum.hexdigest(), str(crc & 0xffffffff)

    def _download_206(self):
        raise NotImplementedError
