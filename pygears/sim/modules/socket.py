import socket
import asyncio
import array
import os
import jinja2
from math import ceil

import itertools
from importlib import util

from pygears.svgen.util import svgen_typedef
from pygears.svgen import svgen
from pygears.definitions import ROOT_DIR
from pygears import registry, GearDone
from pygears.sim.sim_gear import SimGear
from pygears.util.fileio import save_file
from pygears.typing_common.codec import code, decode


def u32_repr_gen(data, dtype):
    yield int(dtype)
    for i in range(ceil(int(dtype) / 32)):
        yield data & 0xffffffff
        data >>= 32


def u32_repr(data, dtype):
    return array.array('I', u32_repr_gen(code(dtype, data), dtype))


def u32_bytes_to_int(data):
    arr = array.array('I')
    arr.frombytes(data)
    val = 0
    for val32 in reversed(arr):
        val <<= 32
        val |= val32

    return val


def u32_bytes_decode(data, dtype):
    return decode(dtype, u32_bytes_to_int(data))


j2_templates = ['runsim.j2', 'top.j2']
j2_file_names = ['run_sim.sh', 'top.sv']


def sv_cosim_gen(gear):
    pygearslib = util.find_spec("pygearslib")
    if pygearslib is not None:
        from pygearslib import sv_src_path
        registry('SVGenSystemVerilogPaths').append(sv_src_path)

    outdir = registry('SimArtifactDir')

    rtl_node = svgen(gear, outdir=outdir)
    sv_node = registry('SVGenMap')[rtl_node]

    port_map = {
        port.basename: port.basename
        for port in itertools.chain(rtl_node.in_ports, rtl_node.out_ports)
    }

    structs = [
        svgen_typedef(port.dtype, f"{port.basename}")
        for port in itertools.chain(rtl_node.in_ports, rtl_node.out_ports)
    ]

    base_addr = os.path.dirname(__file__)
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(base_addr),
        trim_blocks=True,
        lstrip_blocks=True)
    env.globals.update(zip=zip, int=int, print=print, issubclass=issubclass)

    context = {
        'intfs': list(sv_node.sv_port_configs()),
        'module_name': sv_node.sv_module_name,
        'dut_name': sv_node.sv_module_name,
        'dti_verif_path': os.path.abspath(
            os.path.join(ROOT_DIR, 'sim', 'dpi')),
        'param_map': sv_node.params,
        'structs': structs,
        'port_map': port_map,
        'out_path': outdir
    }
    context['includes'] = [
        os.path.abspath(os.path.join(ROOT_DIR, '..', 'svlib', '*.sv'))
    ]

    if pygearslib is not None:
        context['includes'].append(
            os.path.abspath(os.path.join(sv_src_path, '*.sv')))

    for templ, tname in zip(j2_templates, j2_file_names):
        res = env.get_template(templ).render(context)
        fname = save_file(tname, context['out_path'], res)
        if os.path.splitext(fname)[1] == '.sh':
            os.chmod(fname, 0o777)


class SimSocket(SimGear):
    def __init__(self, gear):
        super().__init__(gear)

        sv_cosim_gen(gear)

        # Create a TCP/IP socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # Bind the socket to the port
        server_address = ('localhost', 1234)
        print('starting up on %s port %s' % server_address)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.setblocking(False)

        self.sock.bind(server_address)

        # Listen for incoming connections
        self.sock.listen(len(gear.in_ports) + len(gear.out_ports))
        self.handlers = {}

    async def in_handler(self, conn, pin):
        din = pin.consumer
        try:
            while True:
                async with din as item:
                    pkt = u32_repr(item, din.dtype).tobytes()
                    await self.loop.sock_sendall(conn, pkt)
                    await self.loop.sock_recv(conn, 1024)

        except GearDone as e:
            print(f"SimGear canceling: socket@{pin.basename}")
            del self.handlers[pin]
            conn.send(b'\x00')
            conn.close()

            if not self.handlers:
                self.finish()

            raise e
        except Exception as e:
            print(f"Exception in socket handler: {e}")

    async def out_handler(self, conn, pout):
        dout = pout.producer
        try:
            while True:
                item = await self.loop.sock_recv(conn, 1024)
                if not item:
                    raise GearDone

                print(f"Output data {item}, of len {len(item)}")

                await dout.put(u32_bytes_decode(item, dout.dtype))

        except GearDone as e:
            print(f"SimGear canceling: socket@{pout.basename}")
            del self.handlers[pout]
            dout.finish()
            conn.close()
            if not self.handlers:
                self.finish()

            raise e
        except Exception as e:
            print(f"Exception in socket handler: {e}")

    def make_in_handler(self, name, conn, args):
        try:
            i = self.gear.argnames.index(name)
            return self.gear.in_ports[i], self.loop.create_task(
                self.in_handler(conn, self.gear.in_ports[i]))

        except ValueError as e:
            return None, None

    def make_out_handler(self, name, conn, args):
        try:
            i = self.gear.outnames.index(name)
            return self.gear.out_ports[i], self.loop.create_task(
                self.out_handler(conn, self.gear.out_ports[i]))

        except ValueError as e:
            return None, None

    def finish(self):
        print("Closing socket server")
        super().finish()
        for h in self.handlers.values():
            h.cancel()

        self.sock.close()

    async def func(self, *args, **kwds):
        self.loop = asyncio.get_event_loop()

        print(self.gear.argnames)

        while True:
            print("Wait for connection")
            conn, addr = await self.loop.sock_accept(self.sock)

            msg = await self.loop.sock_recv(conn, 1024)
            port_name = msg.decode()

            print(f"Connection received for {port_name}")

            port, handler = self.make_in_handler(port_name, conn, args)
            if handler is None:
                print("Trying in port")
                port, handler = self.make_out_handler(
                    port_name, conn, args)

            if handler is None:
                print(f"Nonexistant port {port_name}")
                conn.close()
            else:
                self.handlers[port] = handler
