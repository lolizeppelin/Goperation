import sys
import os

from goperation.server.gcenter import run

def main(config_path):
    if not os.path.exists(config_path) or not os.path.isabs(config_path):
        sys.exit("ERROR: Unable to find configuration file via the default")
    run(config_path)