import os

from pygears.hdl.templenv import TemplateEnv
from pygears.core.hier_node import HierYielderBase
from pygears.conf import registry
from pygears.util.fileio import save_file

from .util import vgen_intf, vgen_reg, vgen_wire


class VTemplateEnv(TemplateEnv):
    def __init__(self):
        super().__init__(basedir=os.path.dirname(__file__))

        self.jenv.globals.update(vgen_intf=vgen_intf,
                                 vgen_wire=vgen_wire,
                                 vgen_reg=vgen_reg)

        self.snippets = self.load(self.basedir, 'snippet.j2').module


class VGenGenerateVisitor(HierYielderBase):
    def __init__(self, top, wrapper=False):
        self.vgen_map = registry('vgen/map')
        self.wrapper = wrapper
        self.top = top
        self.template_env = VTemplateEnv()

    def RTLNode(self, node):
        vgen = self.vgen_map.get(node, None)
        if vgen is not None:
            contents = vgen.get_module(self.template_env)
            yield vgen.file_name, contents

            # wrappers not needed for verilog, hence no else


def vgen_generate(top, conf):
    v = VGenGenerateVisitor(top, conf.get('wrapper', False))
    for file_names, contents in v.visit(top):
        if contents:
            if isinstance(contents, (tuple, list)):
                for fn, c in zip(file_names, contents):
                    save_file(fn, conf['outdir'], c)
            else:
                save_file(file_names, conf['outdir'], contents)

    return top
