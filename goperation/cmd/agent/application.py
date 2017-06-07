from goperation.cmd.agent import run as agent_run

from goperation.plugin.manager.rpc.agent.application import ApplicationManager


def run(config_files):
    agent_run(ApplicationManager(), config_files)
