from pygears.typing import TypingNamespacePlugin, typeof
from pygears.typing import Int, Uint, Queue, Tuple, Union


def cast(dtype, cast_type):
    if typeof(cast_type, Int) and (not cast_type.is_specified()):
        if typeof(dtype, Uint):
            return Int[int(dtype) + 1]
        elif typeof(dtype, Int):
            return dtype
        else:
            return Int[int(dtype)]
    if typeof(cast_type, Uint) and (not cast_type.is_specified()):
        if typeof(dtype, Int):
            return Uint[int(dtype) - 1]
        else:
            return Uint[int(dtype)]
    elif typeof(cast_type, Tuple) and (not cast_type.is_specified()):
        if typeof(dtype, Queue) or typeof(dtype, Union):
            return Tuple[dtype[0], dtype[1:]]
    else:
        return cast_type


class CastTypePlugin(TypingNamespacePlugin):
    @classmethod
    def bind(cls):
        cls.registry['TypeArithNamespace']['cast'] = cast
