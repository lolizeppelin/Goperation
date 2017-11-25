from goperation.cmd.agent import run as agent_run

from goperation.manager.rpc.agent.scheduler import SchedulerManager

def run(config_files, config_dirs=None):
    agent_run(SchedulerManager, config_files, config_dirs)
