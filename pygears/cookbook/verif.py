from pygears import gear
from pygears.sim import delay_mon, drv, mon, scoreboard, sim_assert
from pygears.sim.utils import SimDelay


@gear
async def check(din, *, ref):
    try:
        items = []
        while (1):
            items.append(await din.get())
    finally:
        print(f"Here: {items}")
        print(f"{ref}")
        print(f"{items == ref}")
        sim_assert(items == ref)


def tlm_verif(*seq, f, ref):
    res_tlm = tuple(s | drv for s in seq) \
        | f \
        | mon

    ref_tlm = seq | ref

    report = []
    scoreboard(res_tlm, ref_tlm, report=report)

    return report


def verif(*seq, f, ref, delays=None):
    '''Using ref. model'''
    if delays is None:
        delays = [SimDelay(0, 0)] * (len(seq) + 1)
    else:
        assert len(seq) + 1 == len(delays), print(
            'Not enough delays specified')

    stim = tuple(s | drv(delay=delays[i]) for i, s in enumerate(seq))

    res_tlm = stim | f | delay_mon(delay=delays[-1])

    ref_tlm = stim | ref

    report = []
    scoreboard(res_tlm, ref_tlm, report=report)

    return report


def directed(*seq, f, ref):
    '''Directed test, ref is a list of expected results'''
    tuple(s | drv for s in seq) \
        | f \
        | mon \
        | check(ref=ref)


def directed_on_the_fly(*seq, f, ref, delays=None):
    '''Directed test, but checking done on-the-fly (from generators)'''
    if delays is None:
        delays = [SimDelay(0, 0)] * (len(seq) + 1)
    else:
        assert len(seq) + 1 == len(delays), print(
            'Not enough delays specified')

    stim = tuple(s | drv(delay=delays[i]) for i, s in enumerate(seq))

    res_tlm = stim | f | delay_mon(delay=delays[-1])

    report = []
    scoreboard(res_tlm, ref, report=report)

    return report
