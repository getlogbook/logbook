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
after this call will transparently be redirected to Logbook:

.. code-block:: python

    from logbook.compat import redirect_logging

    redirect_logging()

This also means you don't have to call :func:`logging.basicConfig`:

.. testsetup::

    from datetime import datetime, timezone

    set_record_time(datetime(2015, 10, 5, 19, 13, 37, 524346, tzinfo=timezone.utc))

.. doctest::

    >>> from logbook import StreamHandler
    >>> from logbook.compat import redirect_logging
    >>> import sys
    >>> StreamHandler(sys.stdout).push_application()
    >>> redirect_logging()
    >>> from logging import getLogger
    >>> log = getLogger("My Logger")
    >>> log.warning("This is a warning")
    [2015-10-05 19:13:37.524346] WARNING: My Logger: This is a warning

.. testcleanup::

    reset_record_time()

Advanced Setup
--------------

The way this is implemented is with a
:class:`~logbook.compat.RedirectLoggingHandler`.  This class is a handler for
the old logging system that sends records via an internal logbook logger to the
active logbook handlers.  This handler can then be added to specific logging
loggers if you want:

.. testsetup:: advanced

    import logging
    import sys
    from datetime import datetime, timezone

    import logbook

    set_record_time(datetime(2015, 10, 5, 19, 13, 37, 524346, tzinfo=timezone.utc))
    logging.root.handlers.clear()
    null_handler = logbook.NullHandler()
    null_handler.push_context()
    stderr = sys.stderr
    sys.stderr = sys.stdout

.. doctest:: advanced

    >>> from logging import getLogger
    >>> from logbook import StreamHandler
    >>> import sys
    >>> StreamHandler(sys.stdout).push_application()
    >>> mylog = getLogger("My Log")
    >>> from logbook.compat import RedirectLoggingHandler
    >>> mylog.addHandler(RedirectLoggingHandler())
    >>> otherlog = getLogger("Other Log")
    >>> otherlog.warning("logging is deprecated")  # via logging.lastResort
    logging is deprecated
    >>> mylog.warning("but logbook is awesome")
    [2015-10-05 19:13:37.524346] WARNING: My Log: but logbook is awesome

.. testcleanup:: advanced

    sys.stderr = stderr
    null_handler.pop_context()
    reset_record_time()

Reverse Redirects
-----------------

You can also redirect logbook records to logging, so the other way round.
For this you just have to activate the
:class:`~logbook.compat.LoggingHandler` for the thread or application:

.. code-block:: python

    from logbook import Logger
    from logbook.compat import LoggingHandler

    log = Logger("My app")
    with LoggingHandler():
        log.warning("Going to logging")
