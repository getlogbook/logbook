# -*- coding: utf-8 -*-
"""
    logbook
    ~~~~~~~

    Simple logging library that aims to support desktop, command line
    and web applications alike.

    :copyright: (c) 2010 by Armin Ronacher, Georg Brandl.
    :license: BSD, see LICENSE for more details.
"""

from logbook.base import LogRecord, Logger, LoggerGroup, \
     get_level_name, lookup_level, CRITICAL, ERROR, WARNING, INFO, DEBUG, \
     NOTSET
from logbook.handlers import Handler, StreamHandler, FileHandler, \
     StderrHandler, RotatingFileHandler, TimedRotatingFileHandler, \
     TestHandler, MailHandler, iter_context_handlers


# install a default global handler
default_handler = StderrHandler()
default_handler.push_global()
