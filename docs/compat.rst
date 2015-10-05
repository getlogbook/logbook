.. _logging-compat:

Logging Compatibility
=====================

Logbook provides backwards compatibility with the logging library.  When
activated, the logging library will transparently redirect all the logging calls
to your Logbook logging setup.

Basic Setup
-----------

If you import the compat system and call the
:func:`~logbook.compat.redirect_logging` function, all logging calls that happen
after this call will transparently be redirected to Logbook::

    from logbook.compat import redirect_logging
    redirect_logging()

This also means you don't have to call :func:`logging.basicConfig`:

>>> from logbook.compat import redirect_logging, StreamHandler
>>> import sys
>>> StreamHandler(sys.stdout).push_application()
>>> redirect_logging()
>>> from logging import getLogger
>>> log = getLogger('My Logger')
>>> log.warn('This is a warning')
[2015-10-05 19:13:37.524346] WARNING: My Logger: This is a warning

Advanced Setup
--------------

The way this is implemented is with a
:class:`~logbook.compat.RedirectLoggingHandler`.  This class is a handler for
the old logging system that sends records via an internal logbook logger to the
active logbook handlers.  This handler can then be added to specific logging
loggers if you want:

>>> from logging import getLogger, StreamHandler
>>> import sys
>>> StreamHandler(sys.stdout).push_application()
>>> mylog = getLogger('My Log')
>>> from logbook.compat import RedirectLoggingHandler
>>> mylog.addHandler(RedirectLoggingHandler())
>>> otherlog = getLogger('Other Log')
>>> otherlog.warn('logging is deprecated')
No handlers could be found for logger "Other Log"
>>> mylog.warn('but logbook is awesome')
[2015-10-05 19:13:37.524346] WARNING: My Log: but logbook is awesome

Reverse Redirects
-----------------

You can also redirect logbook records to logging, so the other way round.
For this you just have to activate the
:class:`~logbook.compat.LoggingHandler` for the thread or application::

    from logbook import Logger
    from logbook.compat import LoggingHandler

    log = Logger('My app')
    with LoggingHandler():
        log.warn('Going to logging')
