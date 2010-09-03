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
from contextlib import contextmanager


def redirect_logging():
    """Permanently redirects logging to the stdlib.  This also
    removes all otherwise registered handlers on root logger of
    the logging system but leaves the other loggers untouched.
    """
    del logging.root.handlers[:]
    logging.root.addHandler(RedirectLoggingHandler())


@contextmanager
def redirected_logging():
    """Temporarily redirects logging for all threads and reverts
    it later to the old handlers.  Mainly used by the internal
    unittests::

        from logbook.compat import redirected_logging
        with redirected_logging():
            ...
    """
    old_handlers = logging.root.handlers[:]
    redirect_logging()
    try:
        yield
    finally:
        logging.root.handlers[:] = old_handlers


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
                    'processName', 'process'):
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

    def convert_record(self, old_record):
        """Converts an old logging record into a logbook log record."""
        return logbook.LogRecord(old_record.name,
                                 self.convert_level(old_record.levelno),
                                 old_record.getMessage(),
                                 None, None, old_record.exc_info,
                                 self.find_extra(old_record),
                                 self.find_caller(old_record))

    def emit(self, record):
        logbook.dispatch_record(self.convert_record(record))


def redirect_warnings():
    """Like :func:`redirected_warnings` but will redirect all warnings
    to the shutdown of the interpreter::

        from logbook.compat import redirect_warnings
        redirect_warnings()
    """
    redirected_warnings().__enter__()


class redirected_warnings(object):
    """A context manager that copies and restores the warnings filter upon
    exiting the context, and logs warnings using the logbook system.

    The :attr:`~logbook.LogRecord.logger_name` attribute of the log record
    will be the import name of the warning.

    Example usage::

        from logbook.compat import redirected_warnings
        from warnings import warn

        with redirected_warnings():
            warn(DeprecationWarning('logging should be deprecated'))
    """

    def __init__(self):
        self._entered = False

    def message_to_unicode(self, message):
        try:
            return unicode(message)
        except UnicodeError:
            return str(message).decode('utf-8', 'replace')

    def make_record(self, message, exception, filename, lineno):
        category = exception.__name__
        if exception.__module__ != 'exceptions':
            category = exception.__module__ + '.' + category
        rv = logbook.LogRecord(category, logbook.WARNING, message)
        # we don't know the caller, but we get that information from the
        # warning system.  Just attach them.
        rv.filename = filename
        rv.lineno = lineno
        return rv

    def __enter__(self):
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

    def __exit__(self, exc_type, exc_value, tb):
        if not self._entered:  # pragma: no cover
            raise RuntimeError("Cannot exit %r without entering first" % self)
        warnings.filters = self._filters
        warnings.showwarning = self._showwarning
