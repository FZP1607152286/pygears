import itertools
import os

from pygears import config
from pygears.lib.sieve import sieve
from pygears.hdl.sv import SVGenPlugin
from pygears.hdl.sv.svmod import SVModuleInst
from pygears.hdl.modinst import get_port_config
from functools import partial
from pygears.rtl import flow_visitor, RTLPlugin
from pygears.core.gear_inst import GearInstPlugin
from pygears.rtl.gear import RTLGearHierVisitor, is_gear_instance


def index_to_sv_slice(dtype, key):
    subtype = dtype[key]

    if isinstance(key, slice):
        key = min(key.start, key.stop)

    if key is None or key == 0:
        low_pos = 0
    else:
        low_pos = int(dtype[:key])

    high_pos = low_pos + int(subtype) - 1

    return f'{high_pos}:{low_pos}'


def get_sieve_stages_iter(node):
    for s in itertools.chain(getattr(node, 'pre_sieves', []), [node]):
        indexes = s.params['key']
        if not isinstance(indexes, tuple):
            indexes = (indexes, )

        dtype = s.in_ports[0].dtype
        out_type = s.out_ports[0].dtype
        slices = list(
            map(partial(index_to_sv_slice, dtype),
                filter(lambda i: int(dtype[i]) > 0, indexes)))
        yield slices, out_type


def get_sieve_stages(node):
    stages = list(get_sieve_stages_iter(node))
    # If any of the sieves has shrunk data to 0 width, there is nothing to
    # do
    if any(i[0] == [] for i in stages):
        stages = []

    return stages


class SVGenSieve(SVModuleInst):
    @property
    def is_generated(self):
        return not self.memoized or getattr(self.node, 'pre_sieves', [])

    @property
    def port_configs(self):
        if getattr(self.node, 'pre_sieves', []):
            node = getattr(self.node, 'pre_sieves', [])[0]
        else:
            node = self.node

        for p in node.in_ports:
            yield get_port_config('consumer', type_=p.dtype, name=p.basename)

        for p in node.out_ports:
            yield get_port_config('producer', type_=p.dtype, name=p.basename)

    @property
    def template_path(self):
        return os.path.join(os.path.dirname(__file__), 'sieve.j2')

    def get_module(self, template_env):
        if self.memoized and not getattr(self.node, 'pre_sieves', []):
            return None

        context = {
            'stages': get_sieve_stages(self.node),
            'module_name': self.module_name,
            'intfs': list(self.port_configs)
        }

        return template_env.render_local(__file__, "sieve.j2", context)


@flow_visitor
class RemoveEqualReprSieveVisitor(RTLGearHierVisitor):
    def sieve(self, node):
        pout = node.out_ports[0]
        pin = node.in_ports[0]

        if pin.dtype == pout.dtype:
            node.bypass()


@flow_visitor
class CollapseSievesVisitor(RTLGearHierVisitor):
    def sieve(self, node):
        if not hasattr(node, 'pre_sieves'):
            node.pre_sieves = []

        sieve_cons = [
            p for p in node.consumers if is_gear_instance(p.node, sieve)
        ]
        pin = node.in_ports[0]
        pout = node.out_ports[0]
        iin = pin.producer
        iout = pout.consumer

        if sieve_cons:
            # There is a Sieve connected to this Sieve, hence we can combine
            # two of them into a single SV module

            # Connect the consumers of this Sieve, which are Sieves themselves,
            # to this Sieve's predecessor
            for cons_pin in iout.consumers.copy():
                consumer = cons_pin.node
                if is_gear_instance(consumer, sieve):
                    # print(f'Merging {node.name} to {consumer.name}')
                    # print(consumer.params['key'])
                    # If the consumer is a Sieve, just register this Sieve with
                    # it, and short circuit this one
                    consumer.pre_sieves = node.pre_sieves + [node]
                    iout.disconnect(cons_pin)
                    iin.connect(cons_pin)

            # print(f'Remaining conusmer: {[p.node.name for p in node.consumers]}')

            if not node.consumers:
                # Finally, if ther are no consumers left for this sieve remove
                # this Sieve completely (with all it's connections) from the
                # SVGen tree
                node.remove()
                iout.remove()


class RTLSievePlugin(SVGenPlugin, RTLPlugin, GearInstPlugin):
    @classmethod
    def bind(cls):
        cls.registry['svgen']['module_namespace'][sieve] = SVGenSieve
        if not config['gear/memoize']:
            cls.registry['rtl']['flow'].append(CollapseSievesVisitor)
