from simpleutil.automaton import machines
from goperation.filemanager import common

def exitfunc(log):
    def on_exit(old_state, event):
        log.debug("Exiting old state '%s' in response to event '%s'",
                  old_state, event)
    return on_exit


def enterfunc(log):
    def on_enter(new_state, event):
        log.debug("Entering new state '%s' in response to event '%s'",
                  new_state, event)
    return on_enter


def watcherfunc(exitfunc=None, enterfunc=None):
    watchers = {}
    if exitfunc:
        watchers['on_exit'] = exitfunc
    if enterfunc:
        watchers['on_enter'] = enterfunc
    return watchers


def machine(afunc, pfunc, sfunc, rfunc,
            cfunc, efunc=None, watchers=None):
    if not watchers:
        watchers = watcherfunc()
    if not efunc:
        efunc = cfunc

    m = machines.FiniteMachine()
    m.add_state(common.UNDEFINED, **watchers)
    m.add_state(common.SENDING, **watchers)
    m.add_state(common.RECVING, **watchers)
    m.add_state(common.FINISH, terminal=True, **watchers)
    m.add_state(common.ERROR, terminal=True, **watchers)
    m.default_start_state = common.UNDEFINED
    # recv from socket and check token
    m.add_transition(common.UNDEFINED, common.AUTH, common.START)
    # check success,  prepareing buffer
    m.add_transition(common.AUTH, common.PREPAREING, common.OK)
    # prepareing ok, send buffer
    m.add_transition(common.PREPAREING, common.SENDING, common.OK)
    # send buffer ok recv from socket
    m.add_transition(common.SENDING, common.RECVING, common.OK)
    # recv from socket, prepareing buffer
    m.add_transition(common.RECVING, common.PREPAREING, common.OK)
    # send buffer, and over
    m.add_transition(common.SENDING, common.FINISH, common.OVER)
    # recv buffer, and over
    m.add_transition(common.RECVING, common.FINISH, common.OVER)
    # check auth fail
    m.add_transition(common.AUTH, common.ERROR, common.NOT_OK)
    # prepareing fail
    m.add_transition(common.PREPAREING, common.ERROR, common.NOT_OK)
    # send fail
    m.add_transition(common.SENDING, common.ERROR, common.NOT_OK)
    # recv fail
    m.add_transition(common.RECVING, common.ERROR, common.NOT_OK)

    m.add_reaction(common.AUTH, common.START, afunc)
    m.add_reaction(common.PREPAREING, common.OK, pfunc)
    m.add_reaction(common.SENDING, common.OK, sfunc)
    m.add_reaction(common.RECVING, common.OVER, rfunc)
    m.add_reaction(common.FINISH, common.OVER, cfunc)
    m.add_reaction(common.ERROR, common.NOT_OK, efunc)

    return m
