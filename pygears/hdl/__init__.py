import logging
import inspect
import os

from pygears import Intf
from pygears.conf import PluginBase, register_custom_log, reg
from pygears.core.gear import GearPlugin


def register_hdl_paths(*paths):
    for p in paths:
        reg['hdl/include'].append(
            os.path.abspath(os.path.expandvars(os.path.expanduser(p))))

def rename_ambiguous(modname, lang):
    if (modname, lang) in reg['hdlgen/disambig']:
        return f'{modname}_{lang}'

    return modname


def hdl_log():
    return logging.getLogger('svgen')


def mod_lang(module):
    if isinstance(module, Intf):
        lang = None
    else:
        lang = module.params.get('hdl', {}).get('lang', None)

    if lang is not None:
        return lang

    if module is reg['hdl/top']:
        return reg['hdl/lang']

    if module is reg['hdl/top'].parent:
        return reg['hdl/toplang']

    # # TODO: We shouldn't need this?
    # if module.parent is None:
    #     return reg['hdl/lang']

    return mod_lang(module.parent)


def hdlmod(module, lang=None):
    if lang is None:
        lang = mod_lang(module)

    hdlgen_map = reg[f'hdlgen/map']
    if module in hdlgen_map:
        return hdlgen_map[module]

    namespace = reg[f'{lang}gen/module_namespace']

    hdlgen_cls = namespace.get(module.definition, None)

    if hdlgen_cls is None:
        for base_class in inspect.getmro(module.__class__):
            if base_class.__name__ in namespace:
                hdlgen_cls = namespace[base_class.__name__]
                break

    if hdlgen_cls:
        inst = hdlgen_cls(module)
    else:
        inst = None

    hdlgen_map[module] = inst

    return inst


class HDLPlugin(GearPlugin):
    @classmethod
    def bind(cls):
        register_custom_log('hdl', logging.WARNING)
        reg['gear/params/meta'].subreg('hdl')

        reg.confdef('hdl/include', default=[])
        reg.confdef('hdl/lang', default='sv')
        reg.confdef('hdl/toplang', default=None)
        reg['hdl/top'] = None

        reg.confdef('debug/hide_interm_vals', default=True)


from .util import flow_visitor, HDLGearHierVisitor
from .common import list_hdl_files
from . import sv
from . import v
from .hdlgen import hdlgen
from .ipgen import ipgen
from .synth import synth

__all__ = ['hdlgen', 'list_hdl_files', 'flow_visitor']
