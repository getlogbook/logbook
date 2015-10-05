The Design Explained
====================

This part of the documentation explains the design of Logbook in detail.
This is not strictly necessary to make use of Logbook but might be helpful
when writing custom handlers for Logbook or when using it in a more
complex environment.

Dispatchers and Channels
------------------------

Logbook does not use traditional loggers, instead a logger is internally
named as :class:`~logbook.base.RecordDispatcher`.  While a logger also has
methods to create new log records, the base class for all record
dispatchers itself only has ways to dispatch :class:`~logbook.LogRecord`\s
to the handlers.  A log record itself might have an attribute that points
to the dispatcher that was responsible for dispatching, but it does not
have to be.

If a log record was created from the builtin :class:`~logbook.Logger` it
will have the channel set to the name of the logger.  But that itself is
no requirement.  The only requirement for the channel is that it's a
string with some human readable origin information.  It could be
``'Database'`` if the database issued the log record, it could be
``'Process-4223'`` if the process with the pid 4223 issued it etc.

For example if you are logging from the :func:`logbook.log` function they
will have a cannel set, but no dispatcher:

>>> from logbook import TestHandler, warn
>>> handler = TestHandler()
>>> handler.push_application()
>>> warn('This is a warning')
>>> handler.records[0].channel
'Generic'
>>> handler.records[0].dispatcher is None
True

If you are logging from a custom logger, the channel attribute points to
the logger for as long this logger class is not garbage collected:

>>> from logbook import Logger, TestHandler
>>> logger = Logger('Console')
>>> handler = TestHandler()
>>> handler.push_application()
>>> logger.warn('A warning')
>>> handler.records[0].dispatcher is logger
True

You don't need a record dispatcher to dispatch a log record though.  The
default dispatching can be triggered from a function
:func:`~logbook.base.dispatch_record`:

>>> from logbook import dispatch_record, LogRecord, INFO, StreamHandler
>>> import sys
>>> record = LogRecord('My channel', INFO, 'Hello World!')
>>> dispatch_record(record)
[2015-10-05 19:18:52.211472] INFO: My channel: Hello World!

It is pretty common for log records to be created without a dispatcher.
Here some common use cases for log records without a dispatcher:

-   log records that were redirected from a different logging system
    such as the standard library's :mod:`logging` module or the
    :mod:`warnings` module.
-   log records that came from different processes and do not have a
    dispatcher equivalent in the current process.
-   log records that came from over the network.

The Log Record Container
------------------------

The :class:`~logbook.LogRecord` class is a simple container that
holds all the information necessary for a log record.  Usually they are
created from a :class:`~logbook.Logger` or one of the default log
functions (:func:`logbook.warn` etc.) and immediately dispatched to the
handlers.  The logger will apply some additional knowledge to figure out
where the record was created from and if a traceback information should be
attached.

Normally if log records are dispatched they will be closed immediately
after all handlers had their chance to write it down.  On closing, the
interpreter frame and traceback object will be removed from the log record
to break up circular dependencies.

Sometimes however it might be necessary to keep log records around for a
longer time.  Logbook provides three different ways to accomplish that:

1.  Handlers can set the :attr:`~logbook.LogRecord.keep_open` attribute of
    a log record to `True` so that the record dispatcher will not close
    the object.  This is for example used by the
    :class:`~logbook.TestHandler` so that unittests can still access
    interpreter frames and traceback objects if necessary.
2.  Because some information on the log records depends on the interpreter
    frame (such as the location of the log call) it is possible to pull
    that related information directly into the log record so that it can
    safely be closed without losing that information (see
    :meth:`~logbook.LogRecord.pull_information`).
3.  Last but not least, log records can be converted to dictionaries and
    recreated from these.  It is also possible to make these dictionaries
    safe for JSON export which is used by the
    :class:`~logbook.ticketing.TicketingHandler` to store information in a
    database or the :class:`~logbook.more.MultiProcessingHandler` to send
    information between processes.
