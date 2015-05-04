# -*- coding: utf-8 -*-
"""
    logbook.compat
    ~~~~~~~~~~~~~~

    Backwards compatibility with stdlib's logging package and the
    warnings module.

    :copyright: (c) 2010 by Armin Ronacher, Georg Brandl.
    :license: BSD, see LICENSE for more details.
"""
import sys
import logging
import warnings
import logbook
from datetime import date, datetime

from logbook.helpers import u, string_types, iteritems

_epoch_ord = date(1970, 1, 1).toordinal()


def redirect_logging(set_root_logger_level=True):
    """Permanently redirects logging to the stdlib.  This also
    removes all otherwise registered handlers on root logger of
    the logging system but leaves the other loggers untouched.

    :param set_root_logger_level: controls of the default level of the legacy root logger is changed
       so that all legacy log messages get redirected to Logbook
    """
    del logging.root.handlers[:]
    logging.root.addHandler(RedirectLoggingHandler())
    if set_root_logger_level:
        logging.root.setLevel(logging.DEBUG)


class redirected_logging(object):
    """Temporarily redirects logging for all threads and reverts
    it later to the old handlers.  Mainly used by the internal
    unittests::

        from logbook.compat import redirected_logging
        with redirected_logging():
            ...
    """
    def __init__(self, set_root_logger_level=True):
        self.old_handlers = logging.root.handlers[:]
        self.old_level = logging.root.level
        self.set_root_logger_level = set_root_logger_level

    def start(self):
        redirect_logging(self.set_root_logger_level)

    def end(self, etype=None, evalue=None, tb=None):
        logging.root.handlers[:] = self.old_handlers
        logging.root.setLevel(self.old_level)

    __enter__ = start
    __exit__ = end


class LoggingCompatRecord(logbook.LogRecord):

    def _format_message(self, msg, *args, **kwargs):
        assert not kwargs
        return msg % tuple(args)


class RedirectLoggingHandler(logging.Handler):
    """A handler for the stdlib's logging system that redirects
    transparently to logbook.  This is used by the
    :func:`redirect_logging` and :func:`redirected_logging`
    functions.

    If you want to customize the redirecting you can subclass it.
    """

    def __init__(self):
        logging.Handler.__init__(self)

    def convert_level(self, level):
        """Converts a logging level into a logbook level."""
        if level >= logging.CRITICAL:
            return logbook.CRITICAL
        if level >= logging.ERROR:
            return logbook.ERROR
        if level >= logging.WARNING:
            return logbook.WARNING
        if level >= logging.INFO:
            return logbook.INFO
        return logbook.DEBUG

    def find_extra(self, old_record):
        """Tries to find custom data from the old logging record.  The
        return value is a dictionary that is merged with the log record
        extra dictionaries.
        """
        rv = vars(old_record).copy()
        for key in ('name', 'msg', 'args', 'levelname', 'levelno',
                    'pathname', 'filename', 'module', 'exc_info',
                    'exc_text', 'lineno', 'funcName', 'created',
                    'msecs', 'relativeCreated', 'thread', 'threadName',
                    'greenlet', 'processName', 'process'):
            rv.pop(key, None)
        return rv

    def find_caller(self, old_record):
        """Tries to find the caller that issued the call."""
        frm = sys._getframe(2)
        while frm is not None:
            if frm.f_globals is globals() or \
               frm.f_globals is logbook.base.__dict__ or \
               frm.f_globals is logging.__dict__:
                frm = frm.f_back
            else:
                return frm

    def convert_time(self, timestamp):
        """Converts the UNIX timestamp of the old record into a
        datetime object as used by logbook.
        """
        return datetime.utcfromtimestamp(timestamp)

    def convert_record(self, old_record):
        """Converts an old logging record into a logbook log record."""
        record = LoggingCompatRecord(old_record.name,
                                   self.convert_level(old_record.levelno),
                                   old_record.msg, old_record.args,
                                   None, old_record.exc_info,
                                   self.find_extra(old_record),
                                   self.find_caller(old_record))
        record.time = self.convert_time(old_record.created)
        return record

    def emit(self, record):
        logbook.dispatch_record(self.convert_record(record))


class LoggingHandler(logbook.Handler):
    """Does the opposite of the :class:`RedirectLoggingHandler`, it sends
    messages from logbook to logging.  Because of that, it's a very bad
    idea to configure both.

    This handler is for logbook and will pass stuff over to a logger
    from the standard library.

    Example usage::

        from logbook.compat import LoggingHandler, warn
        with LoggingHandler():
            warn('This goes to logging')
    """

    def __init__(self, logger=None, level=logbook.NOTSET, filter=None,
                 bubble=False):
        logbook.Handler.__init__(self, level, filter, bubble)
        if logger is None:
            logger = logging.getLogger()
        elif isinstance(logger, string_types):
            logger = logging.getLogger(logger)
        self.logger = logger

    def get_logger(self, record):
        """Returns the logger to use for this record.  This implementation
        always return :attr:`logger`.
        """
        return self.logger

    def convert_level(self, level):
        """Converts a logbook level into a logging level."""
        if level >= logbook.CRITICAL:
            return logging.CRITICAL
        if level >= logbook.ERROR:
            return logging.ERROR
        if level >= logbook.WARNING:
            return logging.WARNING
        if level >= logbook.INFO:
            return logging.INFO
        return logging.DEBUG

    def convert_time(self, dt):
        """Converts a datetime object into a timestamp."""
        year, month, day, hour, minute, second = dt.utctimetuple()[:6]
        days = date(year, month, 1).toordinal() - _epoch_ord + day - 1
        hours = days * 24 + hour
        minutes = hours * 60 + minute
        seconds = minutes * 60 + second
        return seconds

    def convert_record(self, old_record):
        """Converts a record from logbook to logging."""
        if sys.version_info >= (2, 5):
            # make sure 2to3 does not screw this up
            optional_kwargs = {'func': getattr(old_record, 'func_name')}
        else:
            optional_kwargs = {}
        record = logging.LogRecord(old_record.channel,
                                   self.convert_level(old_record.level),
                                   old_record.filename,
                                   old_record.lineno,
                                   old_record.message,
                                   (), old_record.exc_info,
                                   **optional_kwargs)
        for key, value in iteritems(old_record.extra):
            record.__dict__.setdefault(key, value)
        record.created = self.convert_time(old_record.time)
        return record

    def emit(self, record):
        self.get_logger(record).handle(self.convert_record(record))


def redirect_warnings():
    """Like :func:`redirected_warnings` but will redirect all warnings
    to the shutdown of the interpreter:

    .. code-block:: python

        from logbook.compat import redirect_warnings
        redirect_warnings()
    """
    redirected_warnings().__enter__()


class redirected_warnings(object):
    """A context manager that copies and restores the warnings filter upon
    exiting the context, and logs warnings using the logbook system.

    The :attr:`~logbook.LogRecord.channel` attribute of the log record will be
    the import name of the warning.

    Example usage:

    .. code-block:: python

        from logbook.compat import redirected_warnings
        from warnings import warn

        with redirected_warnings():
            warn(DeprecationWarning('logging should be deprecated'))
    """

    def __init__(self):
        self._entered = False

    def message_to_unicode(self, message):
        try:
            return u(str(message))
        except UnicodeError:
            return str(message).decode('utf-8', 'replace')

    def make_record(self, message, exception, filename, lineno):
        category = exception.__name__
        if exception.__module__ not in ('exceptions', 'builtins'):
            category = exception.__module__ + '.' + category
        rv = logbook.LogRecord(category, logbook.WARNING, message)
        # we don't know the caller, but we get that information from the
        # warning system.  Just attach them.
        rv.filename = filename
        rv.lineno = lineno
        return rv

    def start(self):
        if self._entered:  # pragma: no cover
            raise RuntimeError("Cannot enter %r twice" % self)
        self._entered = True
        self._filters = warnings.filters
        warnings.filters = self._filters[:]
        self._showwarning = warnings.showwarning

        def showwarning(message, category, filename, lineno,
                        file=None, line=None):
            message = self.message_to_unicode(message)
            record = self.make_record(message, category, filename, lineno)
            logbook.dispatch_record(record)
        warnings.showwarning = showwarning

    def end(self, etype=None, evalue=None, tb=None):
        if not self._entered:  # pragma: no cover
            raise RuntimeError("Cannot exit %r without entering first" % self)
        warnings.filters = self._filters
        warnings.showwarning = self._showwarning

    __enter__ = start
    __exit__ = end
