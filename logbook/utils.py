from contextlib import contextmanager
import functools
import sys
import threading

from .base import Logger
from .helpers import string_types
from logbook import debug as logbook_debug


class _SlowContextNotifier(object):

    def __init__(self, threshold, logger_func, args, kwargs):
        self.logger_func = logger_func
        self.args = args
        self.kwargs = kwargs or {}
        self.evt = threading.Event()
        self.threshold = threshold
        self.thread = threading.Thread(target=self._notifier)

    def _notifier(self):
        self.evt.wait(timeout=self.threshold)
        if not self.evt.is_set():
            self.logger_func(*self.args, **self.kwargs)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.evt.set()
        self.thread.join()


def logged_if_slow(message, threshold=1, func=logbook_debug, args=None,
                   kwargs=None):
    """Logs a message (by default using the global debug logger) if a certain
       context containing a set of operations is too slow

    >>> with logged_if_slow('too slow!'):
    ...     ...
    """
    full_args = (message, ) if args is None else (message, ) + tuple(args)
    return _SlowContextNotifier(threshold, func, full_args, kwargs)


class _Local(threading.local):
    enabled = True

_local = _Local()


@contextmanager
def suppressed_deprecations():
    """Disables deprecation messages temporarily

    >>> with suppressed_deprecations():
    ...    call_some_deprecated_logic()
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
    with the correct filename/lineno
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
