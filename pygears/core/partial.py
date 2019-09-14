import functools
import inspect
import sys
from pygears.conf import MultiAlternativeError


def argspec_unwrap(func):
    # uwrp = inspect.unwrap(func, stop=(lambda f: hasattr(f, "__signature__")))
    # return inspect.getfullargspec(uwrp)
    return inspect.getfullargspec(func)


def extract_arg_kwds(kwds, func):
    arg_names, _, varkw, _, kwonlyargs, *_ = argspec_unwrap(func)

    arg_kwds = {}
    kwds_only = {}
    for k in list(kwds.keys()):
        if k in arg_names:
            arg_kwds[k] = kwds[k]
        elif (k in kwonlyargs) or (varkw is not None):
            kwds_only[k] = kwds[k]
        else:
            kwds_only[k] = kwds[k]
            raise TypeError(
                f"{func.__name__}() got an unexpected keyword argument '{k}'")

    return arg_kwds, kwds_only


def combine_arg_kwds(args, kwds, func):
    arg_names, varargs, *_ = argspec_unwrap(func)

    if varargs:
        return args

    args_unmatched = list(args)
    args_comb = []
    for a in arg_names:
        if a in kwds:
            args_comb.append(kwds[a])
        elif args_unmatched:
            args_comb.append(args_unmatched.pop(0))
        else:
            break

    # If some args could not be matched to argument names, raise an Exception
    if args_unmatched:
        raise TypeError(f"Too many positional arguments for {func.__name__}()")

    return args_comb


def all_args_specified(args, func):
    arg_names, varargs, _, _, kwds, _, types = argspec_unwrap(func)
    if varargs:
        return len(args) > 0
    elif len(args) == len(arg_names):
        return True
    else:
        return False


class Partial:
    '''The Partial class implements a mechanism similar to that of the
    functools.partial, with one important difference with how calling
    its objects operates.

    When Partial class is instantiated, arguments that are to be passed to the
    wrapped function are inspected. If not enough positional arguments, as
    demanded by the wrapped function, have been supplied, a Partial object is
    returned that remembers which arguments have been supplied. Otherwise, if
    enough arguments have been supplied, instead of returning a new Partial
    object, the wrapped function is called with the supplied arguments and its
    return value is returned instead.

    When instantiated Partial object is called (via __call__ method), the
    arguments supplied to the call are combined with the arguments already
    supplied via Partial object constructor and Partial class is then called
    with a combined set of arguments to either return a new Partial object or
    call the wrapped function as described by the above paragraph

    This class also supports supplying arguments by pipe '|' operator.

    '''

    def __init__(self, func, *args, **kwds):
        functools.update_wrapper(self, func)
        self.func = func
        self.args = args
        self.kwds = kwds
        self.errors = []

    def __call__(self, *args, **kwds):
        prev_kwds = self.kwds.copy()
        prev_kwds.update(kwds)
        kwds = prev_kwds

        args = self.args + args

        alternatives = [self.func] + getattr(self.func, 'alternatives', [])
        self.errors.clear()

        for func in alternatives:
            try:
                kwd_intfs, kwd_params = extract_arg_kwds(kwds, func)
                args_comb = combine_arg_kwds(args, kwd_intfs, func)

                if all_args_specified(args_comb, func):
                    argspec = argspec_unwrap(func)
                    if '__base__' in argspec.kwonlyargs:
                        kwd_params['__base__'] = self.func
                    return func(*args_comb, **kwd_params)
            except Exception as e:
                # If no alternatives, just re-raise an error
                if len(alternatives) == 1:
                    raise e
                else:
                    # errors.append((func, e, sys.exc_info()))
                    self.errors.append((func, *sys.exc_info()))
        else:
            if len(self.errors) == len(alternatives):
                raise MultiAlternativeError(self.errors)
            else:
                # If some alternative can handle more arguments, try to wait
                # for it
                p = Partial(self.func, *args, **kwds)
                p.errors = self.errors[:]
                return p

    def __matmul__(self, iin):
        return self(intfs=iin)

    def __or__(self, iin):
        return iin.__ror__(self)

    def __ror__(self, iin):
        if type(iin) == tuple:
            return self(*iin)
        else:
            return self(iin)


class Definition:
    '''The Definition class postpones creation of the Partial object on a function
until the function object (definition) has been called to assign first set (or
all) of arguments. This allows for creation of separate Partial objects for
each of the function invocations.

    This class also supports supplying arguments by pipe '|' operator.

    '''

    def __init__(self, func):
        self.func = func

        functools.update_wrapper(self, func)

    def __call__(self, *args, **kwds):
        return Partial(self.func, *args, **kwds)

    def __or__(self, iin):
        module = Partial(self.func)
        return module | iin

    def __ror__(self, iin):
        if isinstance(iin, tuple):
            return Partial(self.func, *iin)
        else:
            return Partial(self.func, iin)
