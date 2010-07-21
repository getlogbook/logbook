"""
Logbook Fork of Logging
"""
# Copyright 2001-2010 by Vinay Sajip. All Rights Reserved.
#
# Copyright 2010 by Armin Ronacher, Georg Brandl.

from __future__ import with_statement

import os
import sys
import time
import codecs
import thread
import warnings
import threading
import traceback
from datetime import datetime
from contextlib import contextmanager
from itertools import izip


CRITICAL = 5
ERROR = 4
WARNING = 3
INFO = 2
DEBUG = 1
NOTSET = 0

_level_names = {
    CRITICAL:   'CRITICAL',
    ERROR:      'ERROR',
    WARNING:    'WARNING',
    INFO:       'INFO',
    DEBUG:      'DEBUG',
    NOTSET:     'NOTSET'
}
_reverse_level_names = dict((v, k) for (k, v) in _level_names.iteritems())
_missing = object()
_main_thread = thread.get_ident()

_global_handlers = []
_context_handler_lock = threading.Lock()
_context_handlers = threading.local()


def iter_context_handlers():
    handlers = list(_global_handlers)
    handlers.extend(getattr(_context_handlers, 'stack', ()))
    return reversed(handlers)


class cached_property(object):

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


def get_level_name(level):
    """Return the textual representation of logging level 'level'."""
    return _level_names.get(level, ('Level %s' % level))


def _lookup_level(level):
    if isinstance(level, (int, long)):
        return level
    try:
        return _reverse_level_names[level]
    except KeyError:
        raise LookupError('unknown level name %s' % level)


class ExtraDict(dict):

    def __missing__(self, key):
        return u''


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
        return self.msg.format(*self.args, **self.kwargs)

    @cached_property
    def time(self):
        return datetime.utcfromtimestamp(self.timestamp)

    @cached_property
    def level_name(self):
        return get_level_name(self.level)

    @cached_property
    def calling_frame(self):
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
        cf = self.calling_frame
        if cf is not None:
            return cf.f_globals.get('__name__')

    @cached_property
    def filename(self):
        cf = self.calling_frame
        if cf is not None:
            return os.path.abspath(cf.f_code.co_filename)

    @cached_property
    def lineno(self):
        cf = self.calling_frame
        if cf is not None:
            return cf.f_lineno

    @cached_property
    def frame_name(self):
        if self.thread == _main_thread:
            return 'MainThread'
        for thread in threading.enumerate():
            if thread.ident == self.thread:
                return thread.name

    @cached_property
    def process_name(self):
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
        if self.exc_info is not None:
            lines = traceback.format_exception(*self.exc_info)
            rv = ''.join(lines).decode('utf-8', 'replace')
            return rv.rstrip()


class Formatter(object):

    def format(self, record):
        pass


class SimpleFormatter(Formatter):
    """
    The SimpleFormatter formats the record according to a single format string
    in str.format() style.  You can access all record attributes using
    ``{record.attribute}`` in the format string.
    """

    def __init__(self, format_string=u'[{record.time:%Y-%m-%d %H:%M}] '
                 u'{record.level_name}: {record.name}: {record.message}'):
        self.format_string = format_string

    def format(self, record):
        rv = self.format_string.format(record=record)
        exc_info = record.format_exception()
        if exc_info is not None:
            rv += u'\n' + exc_info
        return rv


def _level_name_property():
    def _get_level_name(self):
        return get_level_name(self.level)
    def _set_level_name(self, level):
        self.level = _lookup_level(level)
    return property(_get_level_name, _set_level_name)


def _group_reflected_property(name, default):
    def _get(self):
        rv = getattr(self, '_' + name, _missing)
        if rv is not _missing:
            return rv
        if self.group is None:
            return default
        return getattr(self.group, name)
    def _set(self, value):
        setattr(self, '_' + name, value)
    def _del(self):
        delattr(self, '_' + name)
    return property(_get, _set, _del)


class Handler(object):
    """Handler instances dispatch logging events to specific destinations.

    The base handler class. Acts as a placeholder which defines the Handler
    interface. Handlers can optionally use Formatter instances to format
    records as desired. By default, no formatter is specified; in this case,
    the 'raw' message as determined by record.message is logged.
    """

    def __init__(self, level=NOTSET):
        self.name = None
        self.level = _lookup_level(level)
        self.formatter = None

    level_name = _level_name_property()

    def format(self, record):
        """Format the specified record with the formatter on the handler."""
        fmt = self.formatter
        if fmt is not None:
            return fmt.format(record)

    def handle(self, record):
        """Emits and falls back."""
        try:
            self.emit(record)
        except Exception:
            self.handle_error(record, sys.exc_info())

    def emit(self, record):
        """Emit the specified logging record."""

    def close(self):
        """Tidy up any resources used by the handler."""

    def push_context(self, bubble=True):
        """Push the handler for the current context."""
        with _context_handler_lock:
            item = self, bubble
            stack = getattr(_context_handlers, 'stack', None)
            if stack is None:
                _context_handlers.stack = [item]
            else:
                stack.append(item)

    def pop_context(self):
        """Pop the handler from the current context."""
        with _context_handler_lock:
            stack = getattr(_context_handlers, 'stack', None)
            assert stack, 'no handlers on stack'
            assert stack.pop()[0] is self, 'poped unexpected handler'

    def push_global(self, bubble=True):
        """Push the handler to the global stack."""
        _global_handlers.append((self, bubble))

    def pop_global(self):
        """Pop the handler from the global stack."""
        assert _global_handlers, 'no handlers on global stack'
        assert _global_handlers.pop() is self, 'poped unexpected handler'

    @contextmanager
    def contextbound(self, bubble=False):
        self.push_context(bubble)
        try:
            yield
        finally:
            self.pop_context()

    @contextmanager
    def applicationbound(self, bubble=False):
        self.push_global(bubble)
        try:
            yield
        finally:
            self.pop_global()

    def handle_error(self, record, exc_info):
        """Handle errors which occur during an emit() call."""
        try:
            traceback.print_exception(*(exc_info + (None, sys.stderr)))
            sys.stderr.write('Logged from file %s, line %s\n' % (
                             record.filename, record.lineno))
        except IOError:
            pass


class StreamHandler(Handler):
    """a handler class which writes logging records, appropriately formatted,
    to a stream. note that this class does not close the stream, as sys.stdout
    or sys.stderr may be used.
    """

    def __init__(self, stream=None, level=NOTSET):
        Handler.__init__(self, level)
        if stream is None:
            stream = sys.stderr
        self.stream = stream
        self.lock = threading.RLock()

    def close(self):
        # do not close the stream as we didn't open it ourselves, but at least
        # flush
        self.flush()

    def flush(self):
        """Flushes the stream."""
        if self.stream and hasattr(self.stream, 'flush'):
            self.stream.flush()

    def emit(self, record):
        with self.lock:
            msg = self.format(record)
            stream = self.stream
            enc = getattr(stream, 'encoding', None) or 'utf-8'
            stream.write(('%s\n' % msg).encode(enc, 'replace'))
            self.flush()


class FileHandler(StreamHandler):
    """A handler that does the task of opening and closing files for you."""

    def __init__(self, filename, mode='a', encoding=None, level=NOTSET):
        if encoding is not None:
            stream = open(filename, mode)
        else:
            stream = codecs.open(filename, mode, encoding)
        StreamHandler.__init__(self, stream, level)

    def close(self):
        self.flush()
        self.stream.close()


class LazyFileHandler(StreamHandler):
    """A file handler that does not open the file until a record is actually
    written."""

    def __init__(self, filename, mode='a', encoding=None, level=NOTSET):
        StreamHandler.__init__(self, None, level)
        self._filename = filename
        self._mode = mode
        self._encoding = encoding
        self.stream = None

    def _open(self):
        if self._encoding is not None:
            self.stream = open(self._filename, self._mode)
        else:
            self.stream = codecs.open(self._filename, self._mode, self._encoding)

    def close(self):
        if self.stream:
            self.flush()
            self.stream.close()

    def emit(self, record):
        if self.stream is None:
            self._open()
        StreamHandler.emit(self, record)


class TestHandler(Handler):
    """Like a stream handler but keeps the values in memory."""

    def __init__(self, level=NOTSET):
        Handler.__init__(self, level)
        self.formatter = SimpleFormatter(
            u'[{record.level_name}] {record.logger_name}: {record.message}'
        )
        self.records = []
        self._formatted_records = []
        self._formatted_record_cache = []

    def emit(self, record):
        self.records.append(record)

    @property
    def formatted_records(self):
        if len(self._formatted_records) != self.records or \
           any(r1 != r2 for r1, (r2, f) in
               izip(self.records, self._formatted_records)):
            self._formatted_records = map(self.format, self.records)
            self._formatted_record_cache = list(self.records)
        return self._formatted_records

    @property
    def has_criticals(self):
        return any(r.level >= CRITICAL for r in self.records)

    @property
    def has_errors(self):
        return any(ERROR <= r.level < CRITICAL for r in self.records)

    @property
    def has_warnings(self):
        return any(WARNING <= r.level < ERROR for r in self.records)

    @property
    def has_infos(self):
        return any(INFO <= r.level < WARNING for r in self.records)

    @property
    def has_debugs(self):
        return any(DEBUG <= r.level < INFO for r in self.records)

    def has_critical(self, *args, **kwargs):
        kwargs['level'] = CRITICAL
        return self._test_for(*args, **kwargs)

    def has_error(self, *args, **kwargs):
        kwargs['level'] = ERROR
        return self._test_for(*args, **kwargs)

    def has_warning(self, *args, **kwargs):
        kwargs['level'] = WARNING
        return self._test_for(*args, **kwargs)

    def has_info(self, *args, **kwargs):
        kwargs['level'] = INFO
        return self._test_for(*args, **kwargs)

    def has_debug(self, *args, **kwargs):
        kwargs['level'] = DEBUG
        return self._test_for(*args, **kwargs)

    def _test_for(self, message=None, logger_name=None, level=None):
        for record in self.records:
            if level is not None and record.level != level:
                continue
            if logger_name is not None and record.logger_name != logger_name:
                continue
            if message is not None and record.message != message:
                continue
            return True
        return False


class LoggerMixin(object):

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

    def error(self, *args, **kwargs):
        if ERROR >= self.level:
            self._log(ERROR, args, kwargs)

    def exception(self, *args, **kwargs):
        kwargs['exc_info'] = sys.exc_info()
        self.error(msg, args, kwargs)

    def critical(self, *args, **kwargs):
        if CRITICAL >= self.level:
            self._log(CRITICAL, args, kwargs)

    def log(self, level, *args, **kwargs):
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


class Logger(LoggerMixin):
    """Instances of the Logger class reself.level
    present a single logging channel. A
    "logging channel" indicates an area of an application. Exactly how an
    "area" is defined is up to the application developer. Since an
    application can have any number of areas, logging channels are identified
    by a unique string. Application areas can be nested (e.g. an area
    of "input processing" might include sub-areas "read CSV files", "read
    XLS files" and "read Gnumeric files"). To cater for this natural nesting,
    channel names are organized into a namespace hierarchy where levels are
    separated by periods, much like the Java or Python package namespace. So
    in the instance given above, channel names might be "input" for the upper
    level, and "input.csv", "input.xls" and "input.gnu" for the sub-levels.
    There is no arbitrary limit to the depth of nesting.
    """

    def __init__(self, name, level=_missing):
        self.name = name
        self.handlers = []
        self.group = None

    disabled = _group_reflected_property('disabled', False)
    level = _group_reflected_property('level', NOTSET)

    def handle(self, record):
        """Call the handlers for the specified record."""
        if not self.disabled:
            self.call_handlers(record)

    def call_handlers(self, record):
        """Pass a record to all relevant handlers."""
        # logger attached handlers are always handled and before the
        # context specific handlers are running.  There is no way to
        # disable those unless by removing the handlers.
        for handler in self.handlers:
            if record.level >= handler.level:
                handler.handle(record)

        # after that, context specific handlers run (this includes the
        # global handlers)
        for handler, bubble in iter_context_handlers():
            if record.level >= handler.level:
                handler.handle(record)
                if not bubble:
                    break

    def process_record(self, record):
        if self.group is not None:
            self.group.process_record(record)


class LoggerGroup(LoggerMixin):

    def __init__(self, loggers=None, level=NOTSET):
        if loggers is None:
            loggers = []
        self.loggers = loggers
        self.level = _lookup_level(level)
        self.disabled = False

    def add_logger(self, logger):
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

    def __init__(self, logger, save_filters=False):
        self._logger = logger
        self._entered = False
        self._save_filters = save_filters

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
            self._logger.warning("%s", formatted)
        warnings.showwarning = showwarning

    def __exit__(self, *exc_info):
        if not self._entered:
            raise RuntimeError("Cannot exit %r without entering first" % self)
        if self._save_filters:
            warnings.filters = self._filters
        warnings.showwarning = self._showwarning
