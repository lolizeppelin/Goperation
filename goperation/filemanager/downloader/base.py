class DonwerAdapter(object):


    def __init__(self, *args):
        raise NotImplementedError('%s not Implemented' % self.__class__.__name__)


    def download(self, address, dst, timeout):
        raise NotImplementedError
