from contextlib import contextmanager
import functools
import sys
import threading

from .base import Logger, DEBUG
from .helpers import string_types


class _SlowContextNotifier(object):

    def __init__(self, threshold, func):
        self.timer = threading.Timer(threshold, func)

    def __enter__(self):
        self.timer.start()
        return self

    def __exit__(self, *_):
        self.timer.cancel()


_slow_logger = Logger('Slow')


def logged_if_slow(*args, **kwargs):
    """Context manager that logs if operations within take longer than
    `threshold` seconds.

    :param threshold: Number of seconds (or fractions thereof) allwoed before
                      logging occurs. The default is 1 second.
    :param logger: :class:`~logbook.Logger` to use. The default is a 'slow'
                   logger.
    :param level: Log level. The default is `DEBUG`.
    :param func: (Deprecated). Function to call to perform logging.

    The remaining parameters are passed to the
    :meth:`~logbook.base.LoggerMixin.log` method.
    """
    threshold = kwargs.pop('threshold', 1)
    func = kwargs.pop('func', None)
    if func is None:
        logger = kwargs.pop('logger', _slow_logger)
        level = kwargs.pop('level', DEBUG)
        func = functools.partial(logger.log, level, *args, **kwargs)
    else:
        if 'logger' in kwargs or 'level' in kwargs:
            raise TypeError("If using deprecated func parameter, 'logger' and"
                            " 'level' arguments cannot be passed.")
        func = functools.partial(func, *args, **kwargs)

    return _SlowContextNotifier(threshold, func)


class _Local(threading.local):
    enabled = True

_local = _Local()


@contextmanager
def suppressed_deprecations():
    """Disables deprecation messages temporarily

    >>> with suppressed_deprecations():
    ...    call_some_deprecated_logic()

    .. versionadded:: 0.12
    """
    prev_enabled = _local.enabled
    _local.enabled = False
    try:
        yield
    finally:
        _local.enabled = prev_enabled


_deprecation_logger = Logger("deprecation")
_deprecation_locations = set()


def forget_deprecation_locations():
    _deprecation_locations.clear()


def _write_deprecations_if_needed(message, frame_correction):
    if not _local.enabled:
        return
    caller_location = _get_caller_location(frame_correction=frame_correction+1)
    if caller_location not in _deprecation_locations:
        _deprecation_logger.warning(message, frame_correction=frame_correction+1)
        _deprecation_locations.add(caller_location)


def log_deprecation_message(message, frame_correction=0):
    _write_deprecations_if_needed("Deprecation message: {0}".format(message), frame_correction=frame_correction+1)


class _DeprecatedFunction(object):

    def __init__(self, func, message, obj=None, objtype=None):
        super(_DeprecatedFunction, self).__init__()
        self._func = func
        self._message = message
        self._obj = obj
        self._objtype = objtype

    def _get_underlying_func(self):
        returned = self._func
        if isinstance(returned, classmethod):
            if hasattr(returned, '__func__'):
                returned = returned.__func__
            else:
                returned = returned.__get__(self._objtype).__func__
        return returned

    def __call__(self, *args, **kwargs):
        func = self._get_underlying_func()
        warning = "{0} is deprecated.".format(self._get_func_str())
        if self._message is not None:
            warning += " {0}".format(self._message)
        _write_deprecations_if_needed(warning, frame_correction=+1)
        if self._obj is not None:
            return func(self._obj, *args, **kwargs)
        elif self._objtype is not None:
            return func(self._objtype, *args, **kwargs)
        return func(*args, **kwargs)

    def _get_func_str(self):
        func = self._get_underlying_func()
        if self._objtype is not None:
            return '{0}.{1}'.format(self._objtype.__name__, func.__name__)
        return '{0}.{1}'.format(func.__module__, func.__name__)

    def __get__(self, obj, objtype):
        return self.bound_to(obj, objtype)

    def bound_to(self, obj, objtype):
        return _DeprecatedFunction(self._func, self._message, obj=obj,
                                   objtype=objtype)

    @property
    def __name__(self):
        return self._get_underlying_func().__name__

    @property
    def __doc__(self):
        returned = self._get_underlying_func().__doc__
        if returned:  # pylint: disable=no-member
            returned += "\n.. deprecated\n"  # pylint: disable=no-member
            if self._message:
                returned += "   {0}".format(
                    self._message)  # pylint: disable=no-member
        return returned

    @__doc__.setter
    def __doc__(self, doc):
        self._get_underlying_func().__doc__ = doc


def deprecated(func=None, message=None):
    """Marks the specified function as deprecated, and emits a warning when
    it's called.

    >>> @deprecated(message='No longer supported')
    ... def deprecated_func():
    ...     pass

    This will cause a warning log to be emitted when the function gets called,
    with the correct filename/lineno.

    .. versionadded:: 0.12
    """
    if isinstance(func, string_types):
        assert message is None
        message = func
        func = None

    if func is None:
        return functools.partial(deprecated, message=message)

    return _DeprecatedFunction(func, message)


def _get_caller_location(frame_correction):
    frame = sys._getframe(frame_correction + 1)  # pylint: disable=protected-access
    try:
        return (frame.f_code.co_name, frame.f_lineno)
    finally:
        del frame
