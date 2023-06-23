Quickstart
==========

.. currentmodule:: logbook

Logbook makes it very easy to get started with logging.  Just import the logger
class, create yourself a logger and you are set:

>>> from logbook import Logger, StreamHandler
>>> import sys
>>> StreamHandler(sys.stdout).push_application()
>>> log = Logger('My Awesome Logger')
>>> log.warn('This is too cool for stdlib')
[2015-10-05 19:02:03.575723] WARNING: My Awesome Logger: This is too cool for stdlib

A logger is a so-called :class:`~logbook.base.RecordDispatcher`, which is
commonly referred to as a "logging channel".  The name you give such a channel
is up to you and need not be unique although it's a good idea to keep it
unique so that you can filter by it if you want.

The basic interface is similar to what you may already know from the standard
library's :mod:`logging` module.

There are several logging levels, available as methods on the logger.  The
levels -- and their suggested meaning -- are:

* ``critical`` -- for errors that lead to termination
* ``error`` -- for errors that occur, but are handled
* ``warning`` -- for exceptional circumstances that might not be errors
* ``notice`` -- for non-error messages you usually want to see
* ``info`` -- for messages you usually don't want to see
* ``debug`` -- for debug messages

Each of these levels is available as method on the :class:`Logger`.
Additionally the ``warning`` level is aliased as :meth:`~Logger.warn`.

Alternatively, there is the :meth:`~Logger.log` method that takes the logging
level (string or integer) as an argument.

Handlers
--------

Each call to a logging method creates a log *record* which is then passed to
*handlers*, which decide how to store or present the logging info.  There are a
multitude of available handlers, and of course you can also create your own:

* :class:`StreamHandler` for logging to arbitrary streams
* :class:`StderrHandler` for logging to stderr
* :class:`FileHandler`, :class:`MonitoringFileHandler`,
  :class:`RotatingFileHandler` and :class:`TimedRotatingFileHandler` for
  logging to files
* :class:`MailHandler` and :class:`GMailHandler` for logging via e-mail
* :class:`SyslogHandler` for logging to the syslog daemon
* :class:`NTEventLogHandler` for logging to the Windows NT event log

On top of those there are a couple of handlers for special use cases:

* :class:`logbook.FingersCrossedHandler` for logging into memory and
  delegating information to another handler when a certain level was
  exceeded, otherwise discarding all buffered records.
* :class:`logbook.more.TaggingHandler` for dispatching log records that
  are tagged (used in combination with a
  :class:`logbook.more.TaggingLogger`)
* :class:`logbook.queues.ZeroMQHandler` for logging to ZeroMQ
* :class:`logbook.queues.RedisHandler` for logging to Redis
* :class:`logbook.queues.MultiProcessingHandler` for logging from a child
  process to a handler from the outer process.
* :class:`logbook.queues.ThreadedWrapperHandler` for moving the actual
  handling of a handler into a background thread and using a queue to
  deliver records to that thread.
* :class:`logbook.notifiers.GrowlHandler` and
  :class:`logbook.notifiers.LibNotifyHandler` for logging to the OS X Growl
  or the linux notification daemon.
* :class:`logbook.notifiers.BoxcarHandler` for logging to boxcar.io.
* :class:`logbook.more.TwitterHandler` for logging to twitter.
* :class:`logbook.more.ExternalApplicationHandler` for logging to an
  external application such as the OS X ``say`` command.
* :class:`logbook.ticketing.TicketingHandler` for creating tickets from
  log records in a database or other data store.

Registering Handlers
--------------------

So how are handlers registered?  If you are used to the standard Python logging
system, it works a little bit differently here.  Handlers can be registered for
a thread or for a whole process or individually for a logger.  However, it is
strongly recommended not to add handlers to loggers unless there is a very good
use case for that.

If you want errors to go to syslog, you can set up logging like this::

    from logbook import SyslogHandler

    error_handler = SyslogHandler('logbook example', level='ERROR')
    with error_handler.applicationbound():
        # whatever is executed here and an error is logged to the
        # error handler
        ...

This will send all errors to the syslog but warnings and lower record
levels still to stderr.  This is because the handler is not bubbling by
default which means that if a record is handled by the handler, it will
not bubble up to a higher handler.  If you want to display all records on
stderr, even if they went to the syslog you can enable bubbling by setting
*bubble* to ``True``::

    from logbook import SyslogHandler

    error_handler = SyslogHandler('logbook example', level='ERROR', bubble=True)
    with error_handler.applicationbound():
        # whatever is executed here and an error is logged to the
        # error handler but it will also bubble up other handles.
        ...

So what if you want to only log errors to the syslog and nothing to
stderr?  Then you can combine this with a :class:`NullHandler`::

    from logbook import SyslogHandler, NullHandler

    error_handler = SyslogHandler('logbook example', level='ERROR')
    null_handler = NullHandler()

    with null_handler.applicationbound():
        with error_handler.applicationbound():
            # errors now go to the error_handler and everything else
            # is swallowed by the null handler so nothing ends up
            # on the default stderr handler
            ...

Record Processors
-----------------

What makes logbook interesting is the ability to automatically process log
records.  This is handy if you want additional information to be logged for
everything you do.  A good example use case is recording the IP of the current
request in a web application.  Or, in a daemon process you might want to log
the user and working directory of the process.

A context processor can be injected at two places: you can either bind a
processor to a stack like you do with handlers or you can override the
override the :meth:`.RecordDispatcher.process_record` method.

Here an example that injects the current working directory into the
`extra` dictionary of a log record::

    import os
    from logbook import Processor

    def inject_cwd(record):
        record.extra['cwd'] = os.getcwd()

    with my_handler.applicationbound():
        with Processor(inject_cwd).applicationbound():
            # everything logged here will have the current working
            # directory in the log record.
            ...

The alternative is to inject information just for one logger in which case
you might want to subclass it::

    import os

    class MyLogger(logbook.Logger):

        def process_record(self, record):
            logbook.Logger.process_record(self, record)
            record.extra['cwd'] = os.getcwd()


Configuring the Logging Format
------------------------------

All handlers have a useful default log format you don't have to change to use
logbook.  However if you start injecting custom information into log records,
it makes sense to configure the log formatting so that you can see that
information.

There are two ways to configure formatting: you can either just change the
format string or hook in a custom format function.

All the handlers that come with logbook and that log into a string use the
:class:`~logbook.StringFormatter` by default.  Their constructors accept a
format string which sets the :attr:`logbook.Handler.format_string` attribute.
You can override this attribute in which case a new string formatter is set:

>>> from logbook import StderrHandler
>>> handler = StderrHandler()
>>> handler.format_string = '{record.channel}: {record.message}'
>>> handler.formatter
<logbook.handlers.StringFormatter object at 0x100641b90>

Alternatively you can also set a custom format function which is invoked
with the record and handler as arguments:

>>> def my_formatter(record, handler):
...  return record.message
...
>>> handler.formatter = my_formatter

The format string used for the default string formatter has one variable called
`record` available which is the log record itself.  All attributes can be
looked up using the dotted syntax, and items in the `extra` dict looked up
using brackets.  Note that if you are accessing an item in the extra dict that
does not exist, an empty string is returned.

Here is an example configuration that shows the current working directory from
the example in the previous section::

    handler = StderrHandler(format_string=
        '{record.channel}: {record.message) [{record.extra[cwd]}]')

In the :mod:`~logbook.more` module there is a formatter that uses the Jinja2
template engine to format log records, especially useful for multi-line log
formatting such as mails (:class:`~logbook.more.JinjaFormatter`).
