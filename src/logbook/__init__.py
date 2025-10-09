"""
logbook
~~~~~~~

Simple logging library that aims to support desktop, command line
and web applications alike.

:copyright: (c) 2010 by Armin Ronacher, Georg Brandl.
:license: BSD, see LICENSE for more details.
"""

import os
from typing import Any

from .base import (
    CRITICAL,
    DEBUG,
    ERROR,
    INFO,
    NOTICE,
    NOTSET,
    TRACE,
    WARNING,
    Flags,
    Logger,
    LoggerGroup,
    LogRecord,
    NestedSetup,
    Processor,
    dispatch_record,
    get_level_name,
    lookup_level,
    set_datetime_format,
)
from .handlers import (
    BrotliCompressionHandler,
    FileHandler,
    FingersCrossedHandler,
    GMailHandler,
    GroupHandler,
    GZIPCompressionHandler,
    Handler,
    HashingHandlerMixin,
    LimitingHandlerMixin,
    MailHandler,
    MonitoringFileHandler,
    NTEventLogHandler,
    NullHandler,
    RotatingFileHandler,
    StderrHandler,
    StreamHandler,
    StringFormatter,
    StringFormatterHandlerMixin,
    SyslogHandler,
    TestHandler,
    TimedRotatingFileHandler,
    WrapperHandler,
    create_syshandler,
)

# create an anonymous default logger and provide all important
# methods of that logger as global functions
_default_logger = Logger("Generic")
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
if os.environ.get("LOGBOOK_INSTALL_DEFAULT_HANDLER"):
    default_handler = StderrHandler()
    default_handler.push_application()

__all__ = (
    "CRITICAL",
    "DEBUG",
    "ERROR",
    "INFO",
    "NOTICE",
    "NOTSET",
    "TRACE",
    "WARNING",
    "BrotliCompressionHandler",
    "FileHandler",
    "FingersCrossedHandler",
    "Flags",
    "GMailHandler",
    "GZIPCompressionHandler",
    "GroupHandler",
    "Handler",
    "HashingHandlerMixin",
    "LimitingHandlerMixin",
    "LogRecord",
    "Logger",
    "LoggerGroup",
    "MailHandler",
    "MonitoringFileHandler",
    "NTEventLogHandler",
    "NestedSetup",
    "NullHandler",
    "Processor",
    "RotatingFileHandler",
    "StderrHandler",
    "StreamHandler",
    "StringFormatter",
    "StringFormatterHandlerMixin",
    "SyslogHandler",
    "TestHandler",
    "TimedRotatingFileHandler",
    "WrapperHandler",
    "catch_exceptions",
    "create_syshandler",
    "critical",
    "debug",
    "dispatch_record",
    "error",
    "exception",
    "get_level_name",
    "info",
    "log",
    "lookup_level",
    "notice",
    "set_datetime_format",
    "trace",
    "warn",
    "warning",
)


def __getattr__(name: str) -> Any:
    if name != "__version__":
        msg = f"module '{__name__}' has no attribute '{name}'"
        raise AttributeError(msg)

    import warnings
    from importlib.metadata import version

    warnings.warn(
        "logbook.__version__ is deprecated and will be removed in a "
        "future release. Use importlib.metadata instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    return version("Logbook")
