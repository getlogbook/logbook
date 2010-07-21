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
import traceback
import warnings
import thread
import threading
from cStringIO import StringIO
from contextlib import contextmanager
from itertools import izip

from datetime import datetime


CRITICAL = 50
ERROR = 40
WARNING = 30
INFO = 20
DEBUG = 10
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
        self.extra = extra
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
        self.stream.close()

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


class TestHandler(Handler):
    """Like a stream handler but keeps the values in memory."""

    def __init__(self, level=NOTSET):
        Handler.__init__(self, level)
        self.formatter = SimpleFormatter(
            u'[{record.level_name}] {record.logger_name}: {record.message}'
        )
        self.records = []
        self._formatted_records = []

    def emit(self, record):
        self.records.append(record)

    @property
    def formatted_records(self):
        if len(self._formatted_records) != self.records or \
           any(r1 != r2 for r1, (r2, f) in
               izip(self.records, self._formatted_records)):
            self._formatted_records = [(r, self.format(r))
                                       for r in self.records]
        return [f for r, f in self._formatted_records]

    @property
    def has_criticals(self):
        return any(r.level >= CRITICAL for r in self.records)

    @property
    def has_errors(self):
        return any(r.level >= ERROR and r.level < CRITICAL
                   for r in self.records)

    @property
    def has_warnings(self):
        return any(r.level >= WARNING and r.level < ERROR
                   for r in self.records)

    @property
    def has_infos(self):
        return any(r.level >= INFO and r.level < WARNING
                   for r in self.records)

    @property
    def has_debugs(self):
        return any(r.level >= DEBUG and r.level < INFO
                   for r in self.records)

    def has_critical(self, *args, **kwargs):
        kwargs['min_level'] = CRITICAL
        return self._test_for(*args, **kwargs)

    def has_error(self, *args, **kwargs):
        kwargs['min_level'] = ERROR
        kwargs['max_level'] = CRITICAL - 1
        return self._test_for(*args, **kwargs)

    def has_warning(self, *args, **kwargs):
        kwargs['min_level'] = WARNING
        kwargs['max_level'] = ERROR - 1
        return self._test_for(*args, **kwargs)

    def has_info(self, *args, **kwargs):
        kwargs['min_level'] = INFO
        kwargs['max_level'] = WARNING - 1
        return self._test_for(*args, **kwargs)

    def has_debug(self, *args, **kwargs):
        kwargs['min_level'] = DEBUG
        kwargs['max_level'] = INFO - 1
        return self._test_for(*args, **kwargs)

    def _test_for(self, message=None, logger_name=None, min_level=None,
                  max_level=None):
        for record in self.records:
            if min_level is not None and record.level < min_level:
                continue
            if max_level is not None and record.level > max_level:
                continue
            if logger_name is not None and record.logger_name != logger_name:
                continue
            if message is not None and record.message != message:
                continue
            return True
        return False


class Logger(object):
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

    def __init__(self, name, level=NOTSET):
        self.name = name
        self.level = _lookup_level(level)
        self.disabled = False
        self.handlers = []

    level_name = _level_name_property()

    def debug(self, msg, *args, **kwargs):
        if self.is_enabled_for(DEBUG):
            self._log(DEBUG, msg, args, **kwargs)

    def info(self, msg, *args, **kwargs):
        if self.is_enabled_for(INFO):
            self._log(INFO, msg, args, **kwargs)

    def warn(self, msg, *args, **kwargs):
        if self.is_enabled_for(WARNING):
            self._log(WARNING, msg, args, **kwargs)

    def error(self, msg, *args, **kwargs):
        if self.is_enabled_for(ERROR):
            self._log(ERROR, msg, args, **kwargs)

    def exception(self, msg, *args, **kwargs):
        if self.is_enabled_for(ERROR):
            kwargs['exc_info'] = sys.exc_info()
            self.error(msg, *args, **kwargs)

    def critical(self, msg, *args, **kwargs):
        if self.is_enabled_for(CRITICAL):
            self._log(CRITICAL, msg, args, **kwargs)

    def log(self, level, msg, *args, **kwargs):
        if self.is_enabled_for(level):
            self._log(level, msg, args, **kwargs)

    def _log(self, level, msg, args, kwargs=None, exc_info=None, extra=None):
        record = LogRecord(self.name, level, msg, args, kwargs, exc_info,
                           extra, sys._getframe(1))
        try:
            self.handle(record)
        finally:
            record.close()

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

    def is_enabled_for(self, level):
        """Is this logger enabled for level 'level'?"""
        assert isinstance(level, (int, long))
        return level >= self.level


class LoggerAdapter(object):
    """An adapter for loggers which makes it easier to specify contextual
    information in logging output.
    """

    def __init__(self, logger):
        self.logger = logger

    def process(self, msg, kwargs):
        if kwargs['extra'] is None:
            kwargs['extra'] = {}
        self.inject_values(kwargs['extra'])
        return msg, kwargs

    def inject_values(self, extra):
        pass

    def debug(self, msg, *args, **kwargs):
        msg, kwargs = self.process(msg, kwargs)
        self.logger.debug(msg, *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        msg, kwargs = self.process(msg, kwargs)
        self.logger.info(msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        msg, kwargs = self.process(msg, kwargs)
        self.logger.warning(msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        msg, kwargs = self.process(msg, kwargs)
        self.logger.error(msg, *args, **kwargs)

    def exception(self, msg, *args, **kwargs):
        msg, kwargs = self.process(msg, kwargs)
        self.logger.exception(msg, *args, **kwargs)

    def critical(self, msg, *args, **kwargs):
        msg, kwargs = self.process(msg, kwargs)
        self.logger.critical(msg, *args, **kwargs)

    def log(self, level, msg, *args, **kwargs):
        msg, kwargs = self.process(msg, kwargs)
        self.logger.log(level, msg, *args, **kwargs)

    def is_enabled_for(self, level):
        """See if the underlying logger is enabled for the specified level."""
        return self.logger.is_enabled_for(level)


class SimpleLoggerAdapter(LoggerAdapter):
    """Injects a dictionary into the log record's extra dict."""

    def __init__(self, logger, extra):
        super(SimpleLoggerAdapter, self).__init__(logger)
        self.extra = extra

    def inject_values(self, extra):
        extra.update(self.extra)


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


if 0:


    def handle_request(request):
        handler = logbook.Handler()
        handler.add_processor(AddRequestData(request))
        handler.push()
        try:
            pass
        finally:
            handler.pop()
