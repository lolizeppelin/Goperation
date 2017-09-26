# -*- coding: utf-8 -*-
import os
from simpleutil.config import cfg
from goperation.manager.rpc.agent.application.base import AppEndpointBase


test_group = cfg.OptGroup('testopt')



class TestFileManager():
    """测试用 file manager"""

    def __init__(self, update_base):
        self.update_base = update_base

    def get(self, target, download=True, timeout=None):
        for name in os.listdir(self.update_base):
            if name.startswith(target.source):
                return os.path.join(self.update_base, name)
        raise RuntimeError('No file found')


class TestManager(object):
    """测试用 manager"""
    def __init__(self, work_path, update_base=None):
        self.work_path = work_path
        self.filemanager = TestFileManager(update_base)




class TestEndpoint(AppEndpointBase):


    def __init__(self, manager, group):
        self.manager = manager
        self.group = group
        self.target = None
        self.namespace = group.name
        self._home_path = os.path.join(manager.work_path, self.namespace)

    def appname(self, entity):
        return 'app'

    def entity_user(self, entity):
        return None

    def entity_group(self, entity):
        return None

    def entity_home(self, entity):
        return os.path.join(self._home_path, 'entity_%d' % entity)
