from goperation.cmd.agent import run as agent_run

from goperation.manager.rpc.agent.scheduler import SchedulerManager

def run(procname, config_files, config_dirs=None):
    agent_run(procname, SchedulerManager, config_files, config_dirs)
