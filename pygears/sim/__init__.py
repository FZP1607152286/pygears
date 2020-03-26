# from pygears.registry import load_plugin_folder
# import os
# load_plugin_folder(os.path.join(os.path.dirname(__file__), 'modules'))

from functools import partial
from .sim import sim, artifacts_dir, sim_assert, timestep, clk, delta, sim_log, sim_phase, SimFinish
from . import inst

from .sim import SimPlugin, schedule_to_finish

from .extens.vcd import VCD


def verilate(top, *args, **kwds):
    cosim(top, 'verilator', *args, **kwds)


def cosim(top, sim, *args, **kwds):
    from pygears import find, registry

    if top is None:
        top = registry('gear/root')
    elif isinstance(top, str):
        top = find(top)

    if isinstance(sim, str):
        if sim in ['cadence', 'xsim', 'questa']:
            from .modules import SimSocket
            sim_cls = SimSocket
            kwds['sim'] = sim
        elif sim == 'verilator':
            from .modules import SimVerilated
            sim_cls = SimVerilated
        else:
            raise Exception(f"Unsupported simulator: {sim}")
    else:
        sim_cls = sim

    if args or kwds:
        top.params['sim_cls'] = partial(sim_cls, *args, **kwds)
    else:
        top.params['sim_cls'] = sim_cls


__all__ = [
    'sim', 'artifacts_dir', 'sim_assert', 'clk', 'delta', 'timestep', 'sim_log',
    'sim_phase', 'schedule_to_finish', 'SimFinish', 'verilate', 'SimPlugin', 'VCD'
]
