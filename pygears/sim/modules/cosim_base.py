from pygears.sim.sim_gear import SimGear
from pygears.sim import delta, timestep, sim_log, clk
from pygears.conf import Inject, inject
from pygears import GearDone
from .cosim_port import CosimNoData, InCosimPort, OutCosimPort


class CosimBase(SimGear):
    SYNCHRO_HANDLE_NAME = "_synchro"

    @inject
    def __init__(self, gear, timeout=-1, sim_map=Inject('sim/map')):
        super().__init__(gear)
        self.timeout = timeout
        self.in_cosim_ports = [InCosimPort(self, p) for p in gear.in_ports]
        self.out_cosim_ports = [OutCosimPort(self, p) for p in gear.out_ports]
        self.eval_needed = False

        for p in (self.in_cosim_ports + self.out_cosim_ports):
            sim_map[p.port] = p

    def read_out(self, port):
        if self.eval_needed:
            self.handlers[self.SYNCHRO_HANDLE_NAME].forward()

        self.eval_needed = True

        hout = self.handlers[port.basename]
        hout.reset()
        return hout.read()

    def ack_out(self, port):
        self.eval_needed = True
        hout = self.handlers[port.basename]
        hout.ack()
        self.activity_monitor = 0

    def write_in(self, port, data):
        self.eval_needed = True

        hin = self.handlers[port.basename]
        return hin.send(data)

    def reset_out(self, port):
        self.eval_needed = True

        hout = self.handlers[port.basename]
        hout.reset()

    def reset_in(self, port):
        self.eval_needed = True

        hin = self.handlers[port.basename]
        hin.reset()

    def ready_in(self, port):
        if self.eval_needed:
            self.handlers[self.SYNCHRO_HANDLE_NAME].back()
            self.eval_needed = False

        hin = self.handlers[port.basename]
        if hin.ready():
            self.activity_monitor = 0
            return True
        else:
            return False

    async def func(self, *args, **kwds):
        self.activity_monitor = 0
        self.din_pulled = set()
        self.dout_put = set()
        self.prev_timestep = -1
        self.eval_needed = False

        try:
            while True:

                phase = None
                while phase != 'cycle':
                    phase = await delta()

                if self.eval_needed:
                    self.handlers[self.SYNCHRO_HANDLE_NAME].forward()
                    self.eval_needed = False

                if self.activity_monitor == self.timeout:
                    raise GearDone

                self.handlers[self.SYNCHRO_HANDLE_NAME].cycle()
                self.activity_monitor += 1

        except (GearDone, BrokenPipeError):
            # print(f"SimGear canceling: {self.gear.name}")
            for p in self.gear.out_ports:
                p.producer.finish()

            self._finish()
            raise GearDone
