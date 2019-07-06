import inspect
from functools import wraps


def doublewrap(f):
    '''
    a decorator decorator, allowing the decorator to be used as:
    @decorator(with, arguments, and=kwds)
    or
    @decorator
    '''

    @wraps(f)
    def new_dec(*args, **kwds):
        if len(args) == 1 and len(kwds) == 0 and callable(args[0]):
            # actual decorated function
            return f(args[0])
        else:
            # decorator arguments
            return lambda realf: f(realf, *args, **kwds)

    return new_dec


def perpetum(func, *args, **kwds):
    while True:
        yield func(*args, **kwds)


def is_standard_func(func):
    is_async_gen = bool(func.__code__.co_flags & inspect.CO_ASYNC_GENERATOR)
    return not (inspect.iscoroutinefunction(func)
                or inspect.isgeneratorfunction(func) or is_async_gen)
