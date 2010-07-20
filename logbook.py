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

    def __init__(self, name, level, msg, args=None, kwargs=None,
                 exc_info=None, extra=None, frame=None):
        self.timestamp = time.time()
        self.name = name
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
    def formatted_message(self):
        return self.msg.format(*args, **kwargs)

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

    def __init__(self, format_string=u'[{time:%Y-%m-%d %H:%M}] '
                 u'{level_name}: {message}'):
        self.format_string = format_string

    def format(self, record):
        rv = self.format_string.format(record)
        exc_info = record.format_exception()
        if exc_info is not None:
            rv += u'\n' + exc_info
        return rv


def _level_name_property():
    def _get_level_name(self):
        return get_level_name(self.level)
    def _set_level_name(self, value):
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
        self.lock = threading.RLock()

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
        """Emit the specified logging record.

        Wrap the actual emission of the record with acquisition/release of
        the I/O thread lock.
        """

    def flush(self):
        """Ensure all logging output has been flushed.

        This version does nothing and is intended to be implemented by
        subclasses.
        """

    def close(self):
        """Tidy up any resources used by the handler."""

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

    def __init__(self, stream=None):
        Handler.__init__(self)
        if stream is None:
            stream = sys.stderr
        self.stream = stream
        self.lock = threading.RLock()

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


class Logger(object):
    """Instances of the Logger class represent a single logging channel. A
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
        self.parent = None
        self.propagate = 1
        self.handlers = []
        self.disabled = 0

    level_name = _level_name_property()

    def debug(self, msg, *args, **kwargs):
        """
        Log 'msg % args' with severity 'DEBUG'.

        To pass exception information, use the keyword argument exc_info with
        a true value, e.g.

        logger.debug("Houston, we have a %s", "thorny problem", exc_info=1)
        """
        if self.isEnabledFor(DEBUG):
            self._log(DEBUG, msg, args, **kwargs)

    def info(self, msg, *args, **kwargs):
        """
        Log 'msg % args' with severity 'INFO'.

        To pass exception information, use the keyword argument exc_info with
        a true value, e.g.

        logger.info("Houston, we have a %s", "interesting problem", exc_info=1)
        """
        if self.isEnabledFor(INFO):
            self._log(INFO, msg, args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        """
        Log 'msg % args' with severity 'WARNING'.

        To pass exception information, use the keyword argument exc_info with
        a true value, e.g.

        logger.warning("Houston, we have a %s", "bit of a problem", exc_info=1)
        """
        if self.isEnabledFor(WARNING):
            self._log(WARNING, msg, args, **kwargs)

    warn = warning

    def error(self, msg, *args, **kwargs):
        """
        Log 'msg % args' with severity 'ERROR'.

        To pass exception information, use the keyword argument exc_info with
        a true value, e.g.

        logger.error("Houston, we have a %s", "major problem", exc_info=1)
        """
        if self.isEnabledFor(ERROR):
            self._log(ERROR, msg, args, **kwargs)

    def exception(self, msg, *args):
        """
        Convenience method for logging an ERROR with exception information.
        """
        self.error(msg, exc_info=1, *args)

    def critical(self, msg, *args, **kwargs):
        """
        Log 'msg % args' with severity 'CRITICAL'.

        To pass exception information, use the keyword argument exc_info with
        a true value, e.g.

        logger.critical("Houston, we have a %s", "major disaster", exc_info=1)
        """
        if self.isEnabledFor(CRITICAL):
            self._log(CRITICAL, msg, args, **kwargs)

    fatal = critical

    def log(self, level, msg, *args, **kwargs):
        """
        Log 'msg % args' with the integer severity 'level'.

        To pass exception information, use the keyword argument exc_info with
        a true value, e.g.

        logger.log(level, "We have a %s", "mysterious problem", exc_info=1)
        """
        if not isinstance(level, int):
            raise TypeError("level must be an integer")
        if self.isEnabledFor(level):
            self._log(level, msg, args, **kwargs)

    def _log(self, level, msg, args, kwargs=None, exc_info=None, extra=None):
        """
        Low-level logging routine which creates a LogRecord and then calls
        all the handlers of this logger to handle the record.
        """
        record = LogRecord(self.name, level, msg, args, kwargs, exc_info,
                           extra, sys._getframe(1))
        try:
            self.handle(record)
        finally:
            record.close()

    def handle(self, record):
        """
        Call the handlers for the specified record.

        This method is used for unpickled records received from a socket, as
        well as those created locally.
        """
        if not self.disabled:
            self.callHandlers(record)

    def addHandler(self, hdlr):
        """
        Add the specified handler to this logger.
        """
        if not (hdlr in self.handlers):
            self.handlers.append(hdlr)

    def removeHandler(self, hdlr):
        """
        Remove the specified handler from this logger.
        """
        if hdlr in self.handlers:
            #hdlr.close()
            self.handlers.remove(hdlr)

    def callHandlers(self, record):
        """
        Pass a record to all relevant handlers.

        Loop through all handlers for this logger and its parents in the
        logger hierarchy. If no handler was found, output a one-off error
        message to sys.stderr. Stop searching up the hierarchy whenever a
        logger with the "propagate" attribute set to zero is found - that
        will be the last logger whose handlers are called.
        """
        c = self
        found = 0
        while c:
            for hdlr in c.handlers:
                found = found + 1
                if record.level >= hdlr.level:
                    hdlr.handle(record)
            if not c.propagate:
                c = None    #break out
            else:
                c = c.parent

    def getEffectiveLevel(self):
        """
        Get the effective level for this logger.

        Loop through this logger and its parents in the logger hierarchy,
        looking for a non-zero logging level. Return the first one found.
        """
        logger = self
        while logger:
            if logger.level:
                return logger.level
            logger = logger.parent
        return NOTSET

    def isEnabledFor(self, level):
        """
        Is this logger enabled for level 'level'?
        """
        #if self.manager.disable >= level:
        #    return 0
        return level >= self.getEffectiveLevel()

# b/w compat
getLogger = Logger


class LoggerAdapter(object):
    """
    An adapter for loggers which makes it easier to specify contextual
    information in logging output.
    """

    def __init__(self, logger, extra):
        """
        Initialize the adapter with a logger and a dict-like object which
        provides contextual information. This constructor signature allows
        easy stacking of LoggerAdapters, if so desired.

        You can effectively pass keyword arguments as shown in the
        following example:

        adapter = LoggerAdapter(someLogger, dict(p1=v1, p2="v2"))
        """
        self.logger = logger
        self.extra = extra

    def process(self, msg, kwargs):
        """
        Process the logging message and keyword arguments passed in to
        a logging call to insert contextual information. You can either
        manipulate the message itself, the keyword args or both. Return
        the message and kwargs modified (or not) to suit your needs.

        Normally, you'll only need to override this one method in a
        LoggerAdapter subclass for your specific needs.
        """
        kwargs["extra"] = self.extra
        return msg, kwargs

    def debug(self, msg, *args, **kwargs):
        """
        Delegate a debug call to the underlying logger, after adding
        contextual information from this adapter instance.
        """
        msg, kwargs = self.process(msg, kwargs)
        self.logger.debug(msg, *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        """
        Delegate an info call to the underlying logger, after adding
        contextual information from this adapter instance.
        """
        msg, kwargs = self.process(msg, kwargs)
        self.logger.info(msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        """
        Delegate a warning call to the underlying logger, after adding
        contextual information from this adapter instance.
        """
        msg, kwargs = self.process(msg, kwargs)
        self.logger.warning(msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        """
        Delegate an error call to the underlying logger, after adding
        contextual information from this adapter instance.
        """
        msg, kwargs = self.process(msg, kwargs)
        self.logger.error(msg, *args, **kwargs)

    def exception(self, msg, *args, **kwargs):
        """
        Delegate an exception call to the underlying logger, after adding
        contextual information from this adapter instance.
        """
        msg, kwargs = self.process(msg, kwargs)
        kwargs["exc_info"] = 1
        self.logger.error(msg, *args, **kwargs)

    def critical(self, msg, *args, **kwargs):
        """
        Delegate a critical call to the underlying logger, after adding
        contextual information from this adapter instance.
        """
        msg, kwargs = self.process(msg, kwargs)
        self.logger.critical(msg, *args, **kwargs)

    def log(self, level, msg, *args, **kwargs):
        """
        Delegate a log call to the underlying logger, after adding
        contextual information from this adapter instance.
        """
        msg, kwargs = self.process(msg, kwargs)
        self.logger.log(level, msg, *args, **kwargs)

    def isEnabledFor(self, level):
        """
        See if the underlying logger is enabled for the specified level.
        """
        return self.logger.isEnabledFor(level)


BASIC_FORMAT = "%(level_name)s:%(name)s:%(message)s"

def basicConfig(**kwargs):
    """
    Do basic configuration for the logging system.

    This function does nothing if the root logger already has handlers
    configured. It is a convenience method intended for use by simple scripts
    to do one-shot configuration of the logging package.

    The default behaviour is to create a StreamHandler which writes to
    sys.stderr, set a formatter using the BASIC_FORMAT format string, and
    add the handler to the root logger.

    A number of optional keyword arguments may be specified, which can alter
    the default behaviour.

    filename  Specifies that a FileHandler be created, using the specified
              filename, rather than a StreamHandler.
    filemode  Specifies the mode to open the file, if filename is specified
              (if filemode is unspecified, it defaults to 'a').
    format    Use the specified format string for the handler.
    datefmt   Use the specified date/time format.
    level     Set the root logger level to the specified level.
    stream    Use the specified stream to initialize the StreamHandler. Note
              that this argument is incompatible with 'filename' - if both
              are present, 'stream' is ignored.

    Note that you could specify a stream created using open(filename, mode)
    rather than passing the filename and mode in. However, it should be
    remembered that StreamHandler does not close its stream (since it may be
    using sys.stdout or sys.stderr), whereas FileHandler closes its stream
    when the handler is closed.
    """
    # XXX needs to be completely rewritten
    if len(root.handlers) == 0:
        filename = kwargs.get("filename")
        if filename:
            mode = kwargs.get("filemode", 'a')
            hdlr = FileHandler(filename, mode)
        else:
            stream = kwargs.get("stream")
            hdlr = StreamHandler(stream)
        fs = kwargs.get("format", BASIC_FORMAT)
        dfs = kwargs.get("datefmt", None)
        fmt = Formatter(fs, dfs)
        hdlr.setFormatter(fmt)
        root.addHandler(hdlr)
        level = kwargs.get("level")
        if level is not None:
            root.setLevel(level)


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
