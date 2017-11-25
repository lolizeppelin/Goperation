from goperation.cmd.agent import run as agent_run

from goperation.manager.rpc.agent.application import ApplicationManager


def run(config_files, config_dirs=None):
    agent_run(ApplicationManager, config_files, config_dirs)
