# -*- coding: utf-8 -*-
"""
    logbook.compat
    ~~~~~~~~~~~~~~

    Backwards compatibility with stdlib's logging package.

    :copyright: (c) 2010 by Armin Ronacher, Georg Brandl.
    :license: BSD, see LICENSE for more details.
"""

import sys
import logging
import logbook
from contextlib import contextmanager


def redirect_logging():
    """Redirects logging to the stdlib"""
    del logging.root.handlers[:]
    logging.root.addHandler(RedirectLoggingHandler())


@contextmanager
def temporarily_redirected_logging():
    """Temporarily redirects logging for all threads and reverts
    it later to the old handlers.  Mainly used by the internal
    unittests.
    """
    old_handlers = logging.root.handlers[:]
    redirect_logging()
    try:
        yield
    finally:
        logging.root.handlers[:] = old_handlers


class RedirectLoggingHandler(logging.Handler):
    """A handler for the stdlib's logging system that redirects
    transparently to logbook.
    """

    def __init__(self):
        logging.Handler.__init__(self)
        self._logbook_logger = logbook.Logger()

    def convert_level(self, level):
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
        rv = vars(old_record).copy()
        for key in ('name', 'msg', 'args', 'levelname', 'levelno',
                    'pathname', 'filename', 'module', 'exc_info',
                    'exc_text', 'lineno', 'funcName', 'created',
                    'msecs', 'relativeCreated', 'thread', 'threadName',
                    'processName', 'process'):
            rv.pop(key, None)
        return rv

    def find_caller(self):
        frm = sys._getframe(2)
        while frm is not None:
            if frm.f_globals is globals() or \
               frm.f_globals is logbook.base.__dict__ or \
               frm.f_globals is logging.__dict__:
                frm = frm.f_back
            else:
                return frm

    def convert_record(self, old_record):
        return logbook.LogRecord(old_record.name,
                                 self.convert_level(old_record.levelno),
                                 old_record.getMessage(),
                                 None, None, old_record.exc_info,
                                 self.find_extra(old_record),
                                 self.find_caller())

    def emit(self, record):
        converted_record = self.convert_record(record)
        self._logbook_logger.handle(converted_record)
