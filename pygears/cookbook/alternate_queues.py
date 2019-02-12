from pygears import alternative, gear
from pygears.typing import Queue, Uint, bitw


@gear(svgen={'compile': True})
async def alternate_queues(din0: Queue, din1: Queue) -> b'(din0, din1)':
    async for d in din0:
        yield d, None
    async for d in din1:
        yield None, d


@alternative(alternate_queues)
@gear(svgen={'compile': True})
async def alternate_queues_multi(*din: Queue) -> b'(din[0], ) * len(din)':
    i = Uint[bitw(len(din))](0)

    for i, d in enumerate(din):
        async for data in d:
            out_res = [None] * len(din)
            out_res[i] = data
            yield out_res
