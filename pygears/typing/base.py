import collections
import copy
import functools


@functools.lru_cache(maxsize=None)
def index_norm_hashable_single(i, size):
    if isinstance(i, tuple):
        start, stop, step = i

        if step == -1:
            start, stop = stop, start
            if stop is not None:
                if stop == -1:
                    stop = None
                else:
                    stop += 1

            step = 1

        if start is None:
            start = 0
        elif start < 0:
            start += size

        if stop is None:
            stop = size
        elif stop < 0:
            stop += size
        elif stop > size:
            stop = size

        # if start == stop:
        #     raise IndexError

        return slice(start, stop, step)

    else:
        if i < 0:
            i = size + i

        if i >= size:
            raise IndexError

        return i


@functools.lru_cache(maxsize=None)
def index_norm_hashable(index, size):
    return tuple(index_norm_hashable_single(i, size) for i in index)


class TemplateArgumentsError(Exception):
    pass


class TemplatedTypeUnspecified(Exception):
    pass


class TypingMeta(type):
    """Base class all types.
    """
    @property
    def specified(self):
        return True

    def __repr__(self):
        return self.__name__

    def __eq__(self, other):
        return self is other

    def __hash__(self):
        return hash(self.__name__)

    def copy(self):
        return self


def type_repr(obj):
    if isinstance(obj, type) and not isinstance(obj, GenericMeta):
        if obj.__module__ == 'builtins':
            return obj.__qualname__
    if obj is ...:
        return ('...')
    return repr(obj)


def type_str(obj):
    if isinstance(obj, type) and not isinstance(obj, GenericMeta):
        if obj.__module__ == 'builtins':
            return obj.__qualname__
    if obj is ...:
        return ('...')
    return str(obj)


class class_and_instance_method:
    def __init__(self, func):
        self.func = func
        self.__doc__ = func.__doc__

    def __get__(self, instance, cls=None):
        if instance is None:
            # return the metaclass method, bound to the class
            type_ = type(cls)
            return getattr(type_, self.func.__name__).__get__(cls, type_)
        return self.func.__get__(instance, cls)


class GenericMeta(TypingMeta):
    """Base class for all types that have a generic parameter.
    """
    _args = None
    _hash = None
    _base = None
    _specified = None

    def __new__(cls, name, bases, namespace, args=[]):
        # TODO: Throw error when too many args are supplied
        if (not bases) or (not hasattr(bases[0], 'args')) or (not bases[0].args):
            # Form a class that has the generic arguments specified
            if isinstance(args, dict):
                namespace.update(
                    {
                        '__args__': tuple(args.values()),
                        '__parameters__': tuple(args.keys())
                    })
            else:
                namespace.update({'__args__': args})

            namespace.update(
                {
                    '_hash': None,
                    '_base': None,
                    '_specified': None,
                    '_args': None
                })

            return super().__new__(cls, name, bases, namespace)
        else:
            if len(bases[0].templates) < len(args):
                raise TemplateArgumentsError(
                    "Too many arguments to the templated type: {bases[0]}")

            if isinstance(args, dict):
                for t in args:
                    if t not in bases[0].templates:
                        raise TemplateArgumentsError(
                            f"Template parameter '{t}' not part of the "
                            f"templated type: {bases[0]}")

                tmpl_map = args
            else:
                tmpl_map = {name: val for name, val in zip(bases[0].templates, args)}
            return param_subs(bases[0], tmpl_map, {})

    def is_generic(self):
        """Return True if no values have been supplied for the generic parameters.

        >>> Uint.is_generic()
        True

        >>> Uint['template'].is_generic()
        False
        """

        return len(self.args) == 0

    def is_abstract(self):
        return True

    def __bool__(self):
        return self.specified

    def __hash__(self):
        if self._hash is None:
            self._hash = hash(repr(self))

        return self._hash

    @property
    def args_specified(self):
        try:
            if len(self.args) != len(self.__parameters__):
                return False
        except AttributeError:
            pass

        if self.args:
            for a in self.args:
                try:
                    if not a.specified:
                        return False
                except AttributeError:
                    if isinstance(a, (str, bytes)):
                        return False

            return True
        else:
            return False

    @property
    def specified(self):
        """Return True if all generic parameters were supplied concrete values.

        >>> Uint['template'].specified
        False

        >>> Uint[16].specified
        True
        """
        if self._specified is None:
            self._specified = self.args_specified

        return self._specified

    def __getitem__(self, params):
        if isinstance(params, tuple):
            params = list(params)
        elif not isinstance(params, dict):
            params = [params]

        return self.__class__(
            self.__name__, (self, ) + self.__bases__, dict(self.__dict__), args=params)

    @property
    def base(self):
        """Returns base generic class of the type.

        >>> assert Uint[16].base == Uint
        """
        if self._base is None:

            if len(self.__bases__) == 1:
                self._base = self
            else:
                self._base = self.__bases__[-2]

        return self._base

    @property
    def templates(self):
        """Returns a list of templated generic variables within the type. The type is
searched recursively. Each template is reported only once.

        >>> Tuple[Tuple['T1', 'T2'], 'T1'].templates
        ['T1', 'T2']
        """
        def make_unique(seq):
            seen = set()
            return [x for x in seq if x not in seen and not seen.add(x)]

        templates = []
        for a in self.args:
            if hasattr(a, 'templates'):
                a_templates = a.templates
                templates += [v for v in a_templates if v not in templates]
            else:
                if isinstance(a, str):  #and templ_var_re.search(a):
                    templates.append(a)

        return make_unique(templates)

    @property
    def args(self):
        """Returns a list of values supplied for each generic parameter.

        >>> Tuple[Uint[1], Uint[2]].args
        [Uint[1], Uint[2]]
        """

        if self._args is None:
            if hasattr(self, '__args__'):
                if hasattr(self, '__default__'):
                    plen = len(self.__parameters__)
                    alen = len(self.__args__)
                    dlen = len(self.__default__)
                    missing = plen - alen

                    if (missing == 0) or (dlen < missing):
                        self._args = self.__args__
                    else:
                        self._args = self.__args__ + self.__default__[-missing:]
                else:
                    self._args = self.__args__
            else:
                self._args = []

        return self._args

    def __repr__(self):
        if not self.args:
            return super().__repr__()
        else:
            return super().__repr__() + '[%s]' % ', '.join(
                [type_repr(a) for a in self.args])

    def __str__(self):
        if not self.args:
            return super().__repr__()
        else:
            return super().__str__() + '[%s]' % ', '.join(
                [type_str(a) for a in self.args])

    @property
    def fields(self):
        """Returns the names of the generic parameters.

        >>> Tuple[Uint[1], Uint[2]].fields
        ('f0', 'f1')

        >>> Tuple[{'u1': Uint[1], 'u2': Uint[2]}].fields
        ('u0', 'u1')
        """

        if hasattr(self, '__parameters__'):
            return self.__parameters__
        else:
            return [f'f{i}' for i in range(len(self.args))]

    def remove(self, *args):
        args = {k: v for k, v in zip(self.fields, self.args) if k not in args}

        return self.base[args]

    def rename(self, **kwds):
        args = {kwds.get(k, k): v for k, v in zip(self.fields, self.args)}

        return self.base[args]

    def replace(self, **kwds):
        args = {k: kwds.get(k, v) for k, v in zip(self.fields, self.args)}

        return self.base[args]

    def copy(self):
        if hasattr(self, '__parameters__'):
            args = {
                f: a.copy() if is_type(a) else copy.copy(a)
                for f, a in zip(self.fields, self.args)
            }
        else:
            args = tuple(a.copy() if is_type(a) else copy.copy(a) for a in self.args)

        return self.base[args]

    # @functools.lru_cache(maxsize=None)
    def _arg_eq(self, other):
        if len(self.args) != len(other.args):
            return False
        return all(s == o for s, o in zip(self.args, other.args))

    def __eq__(self, other):
        if not isinstance(other, GenericMeta):
            return False

        if self.base is not other.base:
            return False

        if len(self.args) != len(other.args):
            return False

        return all(s == o for s, o in zip(self.args, other.args))


def param_subs(t, matches, namespace):
    t_orig = t

    if isinstance(t, bytes):
        t = t.decode()

    # Did we reach the parameter name?
    if isinstance(t, str):
        try:
            return eval(t, namespace, matches)
        except Exception as e:
            return t_orig
            # raise Exception(
            #     f"{str(e)}\n - while evaluating parameter string '{t}'")

    elif isinstance(t, collections.abc.Iterable):
        return type(t)(param_subs(tt, matches, namespace) for tt in t)
    else:
        if isinstance(t, GenericMeta) and (not t.specified):
            args = [param_subs(t.args[i], matches, namespace) for i in range(len(t.args))]

            if hasattr(t, '__parameters__'):
                args = {name: a for name, a in zip(t.__parameters__, args)}

            return t.__class__(t.__name__, t.__bases__, dict(t.__dict__), args=args)

    return t_orig


class EnumerableGenericMeta(GenericMeta):
    """Base class for all types that are iterable.
    """
    def __int__(self):
        """Calculates the bit width of the type.

        >>> int(Tuple[Uint[1], Uint[2]])
        3
        """
        if self.specified:
            return sum(map(int, self))
        else:
            raise Exception(
                f"Cannot evaluate width of unspecified generic type"
                f" {type_repr(self)}")

    def __len__(self):
        """The number of elements type generates when iterated.

        >>> Uint[16])
        16
        """
        return len(self.keys())

    def keys(self):
        """Returns a list of keys that can be used for indexing the type.
        """
        return list(range(len(self.args)))

    def index_convert(self, index):
        if isinstance(index, str):
            try:
                return self.fields.index(index)
            except ValueError as e:
                raise KeyError(f'Field "{index}" not in type "{repr(self)}"')
        elif not isinstance(index, slice):
            return index
        else:
            return index.__reduce__()[1]

    def index_norm(self, index):
        if not isinstance(index, tuple):
            return (index_norm_hashable_single(self.index_convert(index), len(self)), )
        else:
            return index_norm_hashable(
                tuple(self.index_convert(i) for i in index), len(self))

    def items(self):
        """Generator that yields (key, element) pairs.
        """
        for k in self.keys():
            yield k, self[k]


class Any(metaclass=TypingMeta):
    """Type that can be matched to any other type.
    """
    pass


def typeof(obj, t):
    """Check if a specific type instance is a subclass of the type.

    Args:
       obj: Concrete type instance
       t: Base type class

    """
    try:
        return issubclass(obj, t)
    except TypeError:
        return False


def is_type(obj):
    return isinstance(obj, TypingMeta)
