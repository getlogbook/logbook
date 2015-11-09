# -*- coding: utf-8 -*-
"""
    logbook
    ~~~~~~~

    Simple logging library that aims to support desktop, command line
    and web applications alike.

    :copyright: (c) 2010 by Armin Ronacher, Georg Brandl.
    :license: BSD, see LICENSE for more details.
"""

import os
from .base import (
    LogRecord, Logger, LoggerGroup, NestedSetup,  Processor, Flags,
    get_level_name, lookup_level, dispatch_record, CRITICAL, ERROR, WARNING,
    NOTICE, INFO, DEBUG, TRACE, NOTSET, set_datetime_format)
from .handlers import (
    Handler, StreamHandler, FileHandler, MonitoringFileHandler, StderrHandler,
    RotatingFileHandler, TimedRotatingFileHandler, TestHandler, MailHandler,
    GMailHandler, SyslogHandler, NullHandler, NTEventLogHandler,
    create_syshandler, StringFormatter, StringFormatterHandlerMixin,
    HashingHandlerMixin, LimitingHandlerMixin, WrapperHandler,
    FingersCrossedHandler, GroupHandler)
from . import compat

__version__ = '0.11.4-dev'

# create an anonymous default logger and provide all important
# methods of that logger as global functions
_default_logger = Logger('Generic')
_default_logger.suppress_dispatcher = True
trace = _default_logger.trace
debug = _default_logger.debug
info = _default_logger.info
warn = _default_logger.warn
warning = _default_logger.warning
notice = _default_logger.notice
error = _default_logger.error
exception = _default_logger.exception
catch_exceptions = _default_logger.catch_exceptions
critical = _default_logger.critical
log = _default_logger.log
del _default_logger


# install a default global handler
if os.environ.get('LOGBOOK_INSTALL_DEFAULT_HANDLER'):
    default_handler = StderrHandler()
    default_handler.push_application()
