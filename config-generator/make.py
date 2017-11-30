import os
from simpleutil.config import generator

pwd = os.path.split(__file__)[0]
os.chdir(pwd)

generator.make(cf='goperation.conf')
generator.make(cf='gcenter.conf')
generator.make(cf='agent.conf')