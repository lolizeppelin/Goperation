from goperation.cmd.db.utils import init_manager

dst = {'host': '172.20.0.3',
       'port': 3304,
       'schema': 'manager',
       'user': 'root',
       'passwd': '111111'}

init_manager(dst)