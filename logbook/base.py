# -*- coding: utf-8 -*-
"""
    logbook.base
    ~~~~~~~~~~~~

    Base implementation for logbook.

    :copyright: (c) 2010 by Armin Ronacher, Georg Brandl.
    :license: BSD, see LICENSE for more details.
"""

import os
import sys
import time
import thread
import warnings
import threading
import traceback
from datetime import datetime


CRITICAL = 6
ERROR = 5
WARNING = 4
NOTICE = 3
INFO = 2
DEBUG = 1
NOTSET = 0

_level_names = {
    CRITICAL:   'CRITICAL',
    ERROR:      'ERROR',
    WARNING:    'WARNING',
    NOTICE:     'NOTICE',
    INFO:       'INFO',
    DEBUG:      'DEBUG',
    NOTSET:     'NOTSET'
}
_reverse_level_names = dict((v, k) for (k, v) in _level_names.iteritems())
_missing = object()
_main_thread = thread.get_ident()


class cached_property(object):
    """A property that is lazily calculated and then cached."""

    def __init__(self, func, name=None, doc=None):
        self.__name__ = name or func.__name__
        self.__module__ = func.__module__
        self.__doc__ = doc or func.__doc__
        self.func = func

    def __get__(self, obj, type=None):
        if obj is None:
            return self
        value = obj.__dict__.get(self.__name__, _missing)
        if value is _missing:
            value = self.func(obj)
            obj.__dict__[self.__name__] = value
        return value


def _level_name_property():
    """Returns a property that reflects the level as name from
    the internal level attribute.
    """
    def _get_level_name(self):
        return get_level_name(self.level)
    def _set_level_name(self, level):
        self.level = lookup_level(level)
    return property(_get_level_name, _set_level_name)


def _group_reflected_property(name, default, fallback=_missing):
    """Returns a property for a given name that falls back to the
    value of the group if set.  If there is no such group, the
    provided default is used.
    """
    def _get(self):
        rv = getattr(self, '_' + name, _missing)
        if rv is not _missing and rv != fallback:
            return rv
        if self.group is None:
            return default
        return getattr(self.group, name)
    def _set(self, value):
        setattr(self, '_' + name, value)
    def _del(self):
        delattr(self, '_' + name)
    return property(_get, _set, _del)


def get_level_name(level):
    """Return the textual representation of logging level 'level'."""
    try:
        return _level_names[level]
    except KeyError:
        raise LookupError('unknown level')


def lookup_level(level):
    """Return the integer representation of a logging level."""
    if isinstance(level, (int, long)):
        return level
    try:
        return _reverse_level_names[level]
    except KeyError:
        raise LookupError('unknown level name %s' % level)


class ExtraDict(dict):
    """A dictionary which returns ``u''`` on missing keys."""

    def __missing__(self, key):
        return u''

    def __repr__(self):
        return '%s(%s)' % (
            self.__class__.__name__,
            dict.__repr__(self)
        )


class _ExceptionCatcher(object):
    """Helper for exception caught blocks."""

    def __init__(self, logger, args, kwargs):
        self.logger = logger
        self.args = args
        self.kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, tb):
        if exc_type is not None:
            kwargs = self.kwargs.copy()
            kwargs['exc_info'] = (exc_type, exc_value, tb)
            self.logger.exception(*self.args, **kwargs)
        return True


class LogRecord(object):
    """A LogRecord instance represents an event being logged.

    LogRecord instances are created every time something is logged. They
    contain all the information pertinent to the event being logged. The
    main information passed in is in msg and args
    """
    _pullable_information = ('func_name', 'module', 'filename', 'lineno',
                             'frame_name', 'process_name')

    def __init__(self, logger_name, level, msg, args=None, kwargs=None,
                 exc_info=None, extra=None, frame=None):
        self.timestamp = time.time()
        self.logger_name = logger_name
        self.msg = msg
        self.args = args or ()
        self.kwargs = kwargs or {}
        self.level = level
        self.exc_info = exc_info
        self.extra = ExtraDict(extra or ())
        self.frame = frame
        self.thread = thread.get_ident()
        self.process = os.getpid()
        self._information_pulled = False

    def pull_information(self):
        if self._information_pulled:
            return
        for key in self._pullable_information:
            getattr(self, key)
        self._information_pulled = True

    def close(self):
        self.frame = None
        self.calling_frame = None

    @cached_property
    def message(self):
        """The formatted message."""
        if not (self.args or self.kwargs):
            return self.msg
        try:
            return self.msg.format(*self.args, **self.kwargs)
        except Exception, e:
            # this obviously will not give a proper error message if the
            # information was not pulled and the log record no longer has
            # access to the frame.  But there is not much we can do about
            # that.
            raise TypeError('Could not format message with provided '
                            'arguments: {err}\n  msg=\'{msg}\'\n  args={args} '
                            '\n  kwargs={kwargs}.\n'
                            'Happened in file {file}, line {lineno}'.format(
                err=e, msg=self.msg.encode('utf-8'), args=self.args,
                kwargs=self.kwargs, file=self.filename.encode('utf-8'),
                lineno=self.lineno
            ))

    @cached_property
    def time(self):
        """The time at which the record was logged."""
        return datetime.utcfromtimestamp(self.timestamp)

    @cached_property
    def level_name(self):
        """The name of the record's level."""
        return get_level_name(self.level)

    @cached_property
    def calling_frame(self):
        """The frame in which the record has been created."""
        frm = self.frame
        globs = globals()
        while frm is not None and frm.f_globals is globs:
            frm = frm.f_back
        return frm

    @cached_property
    def func_name(self):
        cf = self.calling_frame
        if cf is not None:
            return cf.f_code.co_name

    @cached_property
    def module(self):
        """The name of the module in which the record has been created."""
        cf = self.calling_frame
        if cf is not None:
            return cf.f_globals.get('__name__')

    @cached_property
    def filename(self):
        """The filename of the module in which the record has been created."""
        cf = self.calling_frame
        if cf is not None:
            return os.path.abspath(cf.f_code.co_filename) \
                .decode(sys.getfilesystemencoding() or 'utf-8', 'replace')

    @cached_property
    def lineno(self):
        """The line number of the file in which the record has been created."""
        cf = self.calling_frame
        if cf is not None:
            return cf.f_lineno

    @cached_property
    def frame_name(self):
        """The name of the frame in which the record has been created."""
        if self.thread == _main_thread:
            return 'MainThread'
        for thread in threading.enumerate():
            if thread.ident == self.thread:
                return thread.name

    @cached_property
    def process_name(self):
        """The name of the process in which the record has been created."""
        # Errors may occur if multiprocessing has not finished loading
        # yet - e.g. if a custom import hook causes third-party code
        # to run when multiprocessing calls import. See issue 8200
        # for an example
        mp = sys.modules.get('multiprocessing')
        if mp is not None:
            try:
                return mp.current_process().name
            except Exception:
                pass

    def format_exception(self):
        """Returns the formatted exception which caused this record to be
        created.
        """
        if self.exc_info is not None:
            lines = traceback.format_exception(*self.exc_info)
            rv = ''.join(lines).decode('utf-8', 'replace')
            return rv.rstrip()


class LoggerMixin(object):
    """
    This mixin defines and implements the "usual" logger interface, i.e.
    a logger that uses the builtin logging levels.

    Classes using this mixin have to implement a :meth:`handle` method which
    takes a :class:`LogRecord` and passes it along.
    """

    #: The name of the minimium logging level required for records to be
    #: created.
    level_name = _level_name_property()

    def debug(self, *args, **kwargs):
        if DEBUG >= self.level:
            self._log(DEBUG, args, kwargs)

    def info(self, *args, **kwargs):
        if INFO >= self.level:
            self._log(INFO, args, kwargs)

    def warn(self, *args, **kwargs):
        if WARNING >= self.level:
            self._log(WARNING, args, kwargs)

    warning = warn

    def notice(self, *args, **kwargs):
        if NOTICE >= self.level:
            self._log(NOTICE, args, kwargs)

    def error(self, *args, **kwargs):
        if ERROR >= self.level:
            self._log(ERROR, args, kwargs)

    def exception(self, *args, **kwargs):
        if 'exc_info' not in kwargs:
            exc_info = sys.exc_info()
            assert exc_info[0] is not None, 'no exception occurred'
            kwargs.setdefault('exc_info', sys.exc_info())
        return self.error(*args, **kwargs)

    def catch_exceptions(self, *args, **kwargs):
        if not args:
            args = ('Uncaught exception occurred',)
        return _ExceptionCatcher(self, args, kwargs)

    def critical(self, *args, **kwargs):
        if CRITICAL >= self.level:
            self._log(CRITICAL, args, kwargs)

    def log(self, level, *args, **kwargs):
        level = lookup_level(level)
        if level >= self.level:
            self._log(level, args, kwargs)

    def process_record(self, record):
        pass

    def _log(self, level, args, kwargs):
        msg, args = args[0], args[1:]
        exc_info = kwargs.pop('exc_info', None)
        extra = kwargs.pop('extra', None)
        record = LogRecord(self.name, level, msg, args, kwargs, exc_info,
                           extra, sys._getframe(1))
        self.process_record(record)
        try:
            self.handle(record)
        finally:
            record.close()


class RecordDispatcher(object):

    def __init__(self, name=None, level=NOTSET):
        self.name = name
        self.handlers = []
        self.group = None
        self.level = level

    disabled = _group_reflected_property('disabled', False)
    level = _group_reflected_property('level', NOTSET, fallback=NOTSET)

    def handle(self, record):
        """Call the handlers for the specified record."""
        if not self.disabled and record.level >= self.level:
            self.call_handlers(record)

    def call_handlers(self, record):
        """Pass a record to all relevant handlers."""
        # logger attached handlers are always handled and before the
        # context specific handlers are running.  There is no way to
        # disable those unless by removing the handlers.  They will
        # always bubble
        for handler in self.handlers:
            if record.level >= handler.level:
                handler.handle(record)

        # after that, context specific handlers run (this includes the
        # global handlers)
        for handler, processor, bubble in iter_context_handlers():
            if handler.should_handle(record):
                # TODO: cloning?  expensive?  document that on bubbling
                # the record is modified for outer processors too?
                if processor is not None:
                    processor(record, handler)
                handler.handle(record)
                if not bubble:
                    break

    def process_record(self, record):
        if self.group is not None:
            self.group.process_record(record)


class Logger(RecordDispatcher, LoggerMixin):
    """Instances of the Logger class represent a single logging channel.
    A "logging channel" indicates an area of an application. Exactly
    how an "area" is defined is up to the application developer.
    """


class LoggerGroup(LoggerMixin):
    """A LoggerGroup represents a group of loggers while behaving like one."""

    def __init__(self, loggers=None, level=NOTSET):
        if loggers is None:
            loggers = []
        self.loggers = loggers
        self.level = lookup_level(level)
        self.disabled = False

    def add_logger(self, logger):
        """Adds a logger to this group."""
        logger.group = self
        self.loggers.append(logger)

    def handle(self, record):
        for logger in self.loggers:
            logger.handle(record)


class log_warnings_to(object):
    """A context manager that copies and restores the warnings filter upon
    exiting the context, and logs warnings using the logbook system.

    The 'record' argument specifies whether warnings should be captured by a
    custom implementation of warnings.showwarning() and be appended to a list
    returned by the context manager. Otherwise None is returned by the context
    manager. The objects appended to the list are arguments whose attributes
    mirror the arguments to showwarning().
    """

    def __init__(self, logger):
        self._logger = logger
        self._entered = False

    def __enter__(self):
        if self._entered:
            raise RuntimeError("Cannot enter %r twice" % self)
        self._entered = True
        if self._save_filters:
            self._filters = warnings.filters
            warnings.filters = self._filters[:]
        self._showwarning = warnings.showwarning
        def showwarning(message, category, filename, lineno,
                        file=None, line=None):
            formatted = warnings.formatwarning(message, category, filename,
                                               lineno, line)
            self._logger.warning(formatted)
        warnings.showwarning = showwarning

    def __exit__(self, *exc_info):
        if not self._entered:
            raise RuntimeError("Cannot exit %r without entering first" % self)
        if self._save_filters:
            warnings.filters = self._filters
        warnings.showwarning = self._showwarning


from logbook.handlers import iter_context_handlers
