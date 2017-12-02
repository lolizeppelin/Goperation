from goperation.cmd.agent import run as agent_run

from goperation.manager.rpc.agent.application import ApplicationManager


def run(procname, config_files, config_dirs=None):
    agent_run(procname, ApplicationManager, config_files, config_dirs)
