import os

class TargetFile(object):

    def __init__(self, source):
        self.source = source
        self.realpath = None

    def clean(self):
        if self.realpath is not None and os.path.exists(self.realpath):
            os.remove(self.realpath)