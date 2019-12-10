# from pygears.conf import safe_bind
from pygears.typing.base import typeof, is_type
from . import Array, Int, Integer, Queue, Tuple, Uint, Union
from . import Fixpnumber, Float, Number, Ufixp, Fixp
# from pygears.conf.log import gear_log


def reinterpret(data, cast_type):
    if is_type(data):
        return cast_type
    else:
        return cast_type.decode(code(data) & ((1 << cast_type.width) - 1))


def code(data, cast_type=Uint):
    if is_type(data):
        if not cast_type.specified and typeof(cast_type, Integer):
            cast_type = cast_type[data.width]

        return cast_type

    dtype = type(data)
    if is_type(dtype):
        data = data.code()
        if not cast_type.specified and typeof(cast_type, Integer):
            cast_type = cast_type[dtype.width]

    if is_type(cast_type) and cast_type.specified:
        return cast_type.decode(data & ((1 << cast_type.width) - 1))
    else:
        return cast_type(data)


def decode(val):
    if is_type(type(val)):
        return val.decode()
    else:
        return val


def short_s(s, cutoff=20):
    if len(s) > cutoff:
        return s[:(cutoff // 2 - 1)] + '...' + s[-(cutoff // 2 - 2):]

    return s


def short_repr(dtype, cutoff=20):
    return short_s(repr(dtype))


def get_type_error(dtype, cast_type, details=None):
    if details is None:
        details = []
    else:
        details = list(details)

    if cast_type.specified:
        details.append(
            f"FIX: to interpret '{short_repr(dtype)}' encoding as '{short_repr(cast_type)}',"
            f" use reinterpret()")
    else:
        details.append(
            f"FIX: to interpret '{short_repr(dtype)}' encoding as '{short_repr(cast_type)}',"
            f" specify the cast type completely and use reinterpret()")

    return TypeError(
        f"Cannot convert type '{repr(dtype)}' to '{repr(cast_type)}'\n    " +
        '\n    '.join(details))


def get_value_error(val, cast_type):
    return ValueError(f"Cannot convert value '{repr(val)}' to '{repr(cast_type)}'")


def uint_type_cast_resolver(dtype, cast_type):
    if typeof(dtype, Ufixp):
        if cast_type.specified:
            if cast_type.width < dtype.integer:
                raise get_type_error(
                    dtype, cast_type, [
                        f"fixed-point integer part (width '{dtype.integer}') is larger than target Uint",
                        f"FIX: to force cast to smaller Uint, cast to generic Uint first and then reinterpret() as '{repr(cast_type)}'"
                    ])

            return cast_type
        elif dtype.integer <= 0:
            raise get_type_error(
                dtype, cast_type, [
                    f"fixed-point has no integer part",
                    f"FIX: to force cast to Uint, supply Uint width explicitly"
                ])
        else:
            return Uint[dtype.integer]

    if typeof(dtype, Uint):
        if not cast_type.specified:
            return dtype
        elif dtype.width > cast_type.width:
            raise get_type_error(
                dtype, cast_type, [f"{repr(dtype)} is larger then {repr(cast_type)}"])
        else:
            return cast_type

    raise get_type_error(dtype, cast_type)


def float_type_cast_resolver(dtype, cast_type):
    if typeof(dtype, Number):
        return cast_type

    raise get_type_error(dtype, cast_type)


def ufixp_type_cast_resolver(dtype, cast_type):
    if typeof(dtype, Ufixp):
        if not cast_type.specified:
            return dtype

        if dtype.integer > cast_type.integer:
            raise get_type_error(dtype, cast_type, [
                f"fixed-point integer part is larger than target's integer part ('{dtype.integer}' > '{cast_type.integer})",
            ])

        if dtype.fract > cast_type.fract:
            raise get_type_error(dtype, cast_type, [
                f"fixed-point fraction part is larger than target's fraction part ('{dtype.fract}' > '{cast_type.fract})",
            ])

        return cast_type

    if typeof(dtype, Uint):
        if not cast_type.specified:
            return Ufixp[dtype.width, dtype.width]

        if dtype.width > cast_type.integer:
            raise get_type_error(dtype, cast_type, [
                f"integer is larger than fixed-point integer part ('{dtype.width}' > '{cast_type.integer})",
            ])

        return cast_type

    raise get_type_error(dtype, cast_type)


def fixp_type_cast_resolver(dtype, cast_type):
    if typeof(dtype, Fixpnumber):
        if not cast_type.specified:
            if dtype.signed:
                return dtype
            else:
                return Fixp[dtype.integer + 1, dtype.width + 1]

        int_part = dtype.integer
        if not dtype.signed:
            int_part += 1

        if int_part > cast_type.integer:
            raise get_type_error(dtype, cast_type, [
                f"needed target's integer part >= {int_part}",
            ])

        if dtype.fract > cast_type.fract:
            raise get_type_error(dtype, cast_type, [
                f"fixed-point fraction part is larger than target's fraction part ('{dtype.fract}' > '{cast_type.fract})",
            ])

        return cast_type

    if typeof(dtype, Integer):
        dtype = type_cast(dtype, Int)

        if not cast_type.specified:
            return Fixp[dtype.width, dtype.width]

        if dtype.width > cast_type.integer:
            raise get_type_error(dtype, cast_type, [
                f"integer is larger than fixed-point integer part ('{dtype.width}' > '{cast_type.integer})",
            ])

        return cast_type

    raise get_type_error(dtype, cast_type)


def int_type_cast_resolver(dtype, cast_type):
    if typeof(dtype, Fixpnumber):
        int_part = dtype.integer
        if not dtype.signed:
            int_part += 1

        if cast_type.specified:
            if not dtype.signed and cast_type.width == dtype.integer:
                raise get_type_error(
                    dtype, cast_type, (
                        f"Int needs to be one bit larger (width {int_part}) to represent unsigned fixed-point integer part (width {dtype.integer})",
                        f"FIX: to force cast to smaller Int, cast to generic Int first and then reinterpret() as '{repr(cast_type)}'"
                    ))

            elif cast_type.width < dtype.integer:
                raise get_type_error(
                    dtype, cast_type, (
                        f"fixed-point integer part (width '{dtype.integer}') is larger than target Int",
                        f"FIX: to force cast to smaller Int, cast to generic Int first and then reinterpret() as '{repr(cast_type)}'"
                    ))

            return cast_type
        elif dtype.integer <= 0:
            raise get_type_error(
                dtype, cast_type, (
                    f"fixed-point has no integer part",
                    f"FIX: to force cast to Int, supply Int width explicitly"))
        else:
            return Int[int_part]

    if typeof(dtype, Integer):
        width = dtype.width
        if not dtype.signed:
            width += 1

        if not cast_type.specified:
            return Int[width]
        elif not dtype.signed and cast_type.width == dtype.width:
            raise get_type_error(
                dtype, cast_type, (
                    f"Int needs to be one bit larger (width {width}) to represent unsigned integer (width {dtype.width})",
                    f"FIX: to force cast to smaller Int, cast to generic Int first and then reinterpret() as '{repr(cast_type)}'"
                ))
        elif cast_type.width < dtype.width:
            raise get_type_error(
                dtype, cast_type, [f"{repr(dtype)} is larger then {repr(cast_type)}"])
        else:
            return cast_type

    raise get_type_error(dtype, cast_type)


def plain_int_type_cast_resolver(dtype, cast_type):
    if typeof(dtype, (Uint, Int)):
        return int

    raise get_type_error(dtype, cast_type)


def tuple_type_cast_resolver(dtype, cast_type):
    if typeof(dtype, Tuple) and len(cast_type) == 0:
        return dtype

    if typeof(dtype, (Queue, Union, Tuple)):
        fields = [d for d in dtype]
    elif typeof(dtype, Array):
        fields = [dtype.data] * len(dtype)
    else:
        raise get_type_error(dtype, cast_type)

    if len(cast_type) == 0:
        return Tuple[tuple(fields)]
    elif len(cast_type) != len(fields):
        comp = 'less' if len(cast_type) < len(fields) else 'more'
        raise get_type_error(
            dtype, cast_type, [
                f"target Tuple has {comp} elements ({len(cast_type)}) than needed ({len(fields)})"
            ])
    else:
        try:
            cast_fields = [cast(dt, ct) for dt, ct in zip(fields, cast_type.args)]
        except TypeError as e:
            raise TypeError(
                f"{str(e)}\n    - when casting '{repr(dtype)}' to '{repr(cast_type)}'")

        return Tuple[tuple(cast_fields)]

    raise get_type_error(dtype, cast_type)


def array_type_cast_resolver(dtype, cast_type):
    if (typeof(dtype, Array) and (len(cast_type.args) == 0)):
        return dtype

    if typeof(dtype, Tuple):
        if len(cast_type.args) >= 1:
            arr_dtype = cast(dtype.args[0], cast_type.dtype)
        else:
            arr_dtype = dtype.args[0]

        if len(cast_type.args) == 2:
            if len(dtype) != len(cast_type):
                comp = 'less' if len(cast_type) < len(dtype) else 'more'
                raise get_type_error(
                    dtype, cast_type, [
                        f"target Array has {comp} elements ({len(cast_type)}) than Tuple ({len(dtype)})"
                    ])

        try:
            for t in dtype.args:
                cast(t, arr_dtype)
        except TypeError as e:
            raise TypeError(
                f"{str(e)}\n    - when casting '{repr(dtype)}' to '{repr(cast_type)}'")

        return Array[arr_dtype, len(dtype)]

    raise get_type_error(dtype, cast_type)


def union_type_cast_resolver(dtype, cast_type):
    if (typeof(dtype, Union) and (len(cast_type.args) == 0)):
        return dtype

    if typeof(dtype, Tuple):
        if len(dtype) != 2:
            raise get_type_error(
                dtype, cast_type,
                [f"only Tuple with exactly 2 elements can be converted to Union"])

        if len(cast_type.types) != 0:
            cast_ctrl = cast_type.ctrl
            types = tuple(cast_type.types)

            if cast_type.data.width < dtype.args[0].width:
                raise get_type_error(
                    dtype, cast_type,
                    [f"Tuple first element larger than target Union data field"])

            try:
                ctrl = cast(dtype.args[1], cast_ctrl)
            except TypeError as e:
                raise TypeError(
                    f"{str(e)}\n    - when casting '{repr(dtype)}' to '{repr(cast_type)}'")
        else:
            ctrl = cast(dtype.args[1], Uint)
            types = (dtype.args[0], ) * (2**ctrl.width)

        res = Union[types]

        # if ctrl.width > 6:
        #     gear_log().warning(
        #         f'Casting to large Union with {2**ctrl.width}'
        #         f' subtypes from {dtype}')

        return res

    raise get_type_error(dtype, cast_type)


def queue_type_cast_resolver(dtype, cast_type):
    if (typeof(dtype, Queue) and (len(cast_type.args) == 0)):
        return dtype

    if typeof(dtype, Tuple):
        if len(dtype) != 2:
            raise get_type_error(
                dtype, cast_type,
                [f"only Tuple with exactly 2 elements can be converted to Queue"])

        lvl = cast(dtype[1], Uint).width
        if len(cast_type.args) != 0:
            if cast_type.lvl != lvl:
                raise get_type_error(
                    dtype, cast_type, [
                        f"second Tuple element width ({lvl}) must match Queue level ({cast_type.lvl})"
                    ])

            try:
                data = cast(dtype.args[0], cast_type.data)
            except TypeError as e:
                raise TypeError(
                    f"{str(e)}\n    - when casting '{repr(dtype)}' to '{repr(cast_type)}'")
        else:
            data = dtype.args[0]

        return Queue[data, lvl]

    raise get_type_error(dtype, cast_type)


type_cast_resolvers = {
    Uint: uint_type_cast_resolver,
    Int: int_type_cast_resolver,
    Ufixp: ufixp_type_cast_resolver,
    Fixp: fixp_type_cast_resolver,
    Tuple: tuple_type_cast_resolver,
    Union: union_type_cast_resolver,
    Float: float_type_cast_resolver,
    Array: array_type_cast_resolver,
    Queue: queue_type_cast_resolver,
    int: plain_int_type_cast_resolver
}


def type_cast(dtype, cast_type):
    if dtype == cast_type:
        return dtype

    for templ in type_cast_resolvers:
        if typeof(cast_type, templ):
            return type_cast_resolvers[templ](dtype, cast_type)

    raise TypeError(f"Cannot cast '{repr(dtype)}' to '{repr(cast_type)}'")


def integer_value_cast_resolver(val, cast_type):
    if typeof(type(val), Integer):
        if not cast_type.specified:
            cast_type = cast_type[val.width]

        tout_range = (1 << int(cast_type))
        val = int(val) & (tout_range - 1)

        if typeof(cast_type, Int):
            max_uint = tout_range / 2 - 1
            if val > max_uint:
                val -= tout_range

        return cast_type(val)

    raise get_value_error(val, cast_type)


def uint_value_cast_resolver(val, cast_type):
    val_type = type(val)
    if not is_type(val_type) and isinstance(val, (int, float)):
        return cast_type(int(val))

    cast_type = uint_type_cast_resolver(val_type, cast_type)

    if typeof(val_type, Ufixp):
        if val_type.fract >= 0:
            return cast_type.decode(val.code() >> val_type.fract)
        else:
            return cast_type.decode(val.code() << (-val_type.fract))

    if typeof(val_type, Uint):
        return cast_type(val)

    raise get_value_error(val, cast_type)


def int_value_cast_resolver(val, cast_type):
    val_type = type(val)
    if not is_type(val_type) and isinstance(val, (int, float)):
        return cast_type(int(val))

    cast_type = int_type_cast_resolver(val_type, cast_type)

    if typeof(val_type, Fixpnumber):
        if val_type.fract >= 0:
            return cast_type.decode(val.code() >> val_type.fract)
        else:
            return cast_type.decode(val.code() << (-val_type.fract))

    if typeof(val_type, Integer):
        return cast_type(val)

    raise get_value_error(val, cast_type)


def plain_int_value_cast_resolver(val, cast_type):
    return int(val)


def tuple_value_cast_resolver(val, cast_type):
    if (isinstance(val, (list, tuple, dict)) and not is_type(type(val))
            and not cast_type.specified):
        return cast_type(val)

    val_type = type(val)
    cast_type = tuple_type_cast_resolver(val_type, cast_type)

    return cast_type(tuple(cast(v, ct) for v, ct in zip(val, cast_type)))


def array_value_cast_resolver(val, cast_type):
    val_type = type(val)
    cast_type = array_type_cast_resolver(val_type, cast_type)

    return cast_type(tuple(cast(v, cast_type.data) for v in val))


def union_value_cast_resolver(val, cast_type):
    val_type = type(val)
    cast_type = union_type_cast_resolver(val_type, cast_type)

    return cast_type(tuple(cast(v, cast_type.data) for v in val))


def queue_value_cast_resolver(val, cast_type):
    val_type = type(val)
    cast_type = queue_type_cast_resolver(val_type, cast_type)

    return cast_type(tuple(cast(v, cast_type.data) for v in val))


def fixpnumber_value_cast_resolver(val, cast_type):
    val_type = type(val)
    cast_type = type_cast(val_type, cast_type)

    return cast_type(val)


def float_value_cast_resolver(val, cast_type):
    if typeof(type(val), (int, float, Number)):
        return cast_type(val)

    raise Exception(
        f'Only numbers can be converted to Float, not {val} of the type'
        f' {repr(type(val))}')


value_cast_resolvers = {
    Uint: uint_value_cast_resolver,
    Int: int_value_cast_resolver,
    Integer: integer_value_cast_resolver,
    Tuple: tuple_value_cast_resolver,
    Array: array_value_cast_resolver,
    Union: union_value_cast_resolver,
    Float: float_value_cast_resolver,
    Fixpnumber: fixpnumber_value_cast_resolver,
    Queue: queue_value_cast_resolver,
    int: plain_int_value_cast_resolver,
}


def value_cast(val, cast_type):
    if type(val) == cast_type:
        return val

    for templ in value_cast_resolvers:
        if typeof(cast_type, templ):
            return value_cast_resolvers[templ](val, cast_type)

    raise ValueError(
        f"Type '{repr(cast_type)}' unsupported, cannot cast value '{val}' "
        f"of type '{repr(type(val))}'")


def cast(data, cast_type):
    if is_type(data):
        return type_cast(data, cast_type)
    else:
        return value_cast(data, cast_type)


def signed(dtype_or_val):
    if dtype_or_val.signed:
        return dtype_or_val

    if is_type(dtype_or_val):
        if typeof(dtype_or_val, Uint):
            return cast(dtype_or_val, Int)


def reinterpret(data, cast_type):
    if is_type(data):
        return cast_type
    else:
        if typeof(cast_type, (Uint, Int)) and not cast_type.specified:
            cast_type = cast_type[type(data).width]

        return cast_type.decode(code(data) & ((1 << cast_type.width) - 1))


# class CastCoreTypesPlugin(CoreTypesPlugin):
#     @classmethod
#     def bind(cls):
#         safe_bind('gear/type_arith/cast', cast)
