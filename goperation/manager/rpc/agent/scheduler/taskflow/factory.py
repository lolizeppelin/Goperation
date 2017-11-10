from simpleflow.retry import Times
from simpleflow.patterns import linear_flow as lf

from goperation.manager.rpc.agent.scheduler.taskflow import executor
from goperation.manager.rpc.agent.scheduler.taskflow import analyzer


def flow_factory(job):
    """
    @param job:                 class: sqlalchemy:session
    """
    retryer = None
    if job.retry:
        retryer = Times(attempts=job.retry, revert_all=job.revertall)
    main_flow = lf.Flow('scheduler_taskflow', retry=retryer)
    for index, step in enumerate(job.steps):
        _executor = getattr(executor, step.executor)
        _analyzer = getattr(analyzer, step.executor)
        task_executor = _executor or _analyzer
        task = task_executor.builder('%d-%d' % (job.job_id, index), step)
        main_flow.add(task)
    return main_flow


def start_taskflow(job):
    pass