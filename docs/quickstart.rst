Quickstart
==========

.. currentmodule:: logbook

Logbook makes it very easy to get started with logging.  Just import the logger
class, create yourself a logger and you are set:

>>> from logbook import Logger
>>> log = Logger('My Awesome Logger')
>>> log.warn('This is too cool for stdlib')
[2010-07-23 16:34] WARNING: My Awesome Logger: This is too cool for stdlib

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
Additionally the ``warning`` level is aliases :meth:`~Logger.warn`.

Alternatively, there is the :meth:`~Logger.log` method that takes the logging
level (string or integer) as an argument.

Handlers
--------

Each call to a logging method creates a log *record* which is then passed to
*handlers*, which decide how to store or present the logging info.  There is a
multitude of available handlers, and of course you can also create your own:

* :class:`StreamHandler` for logging to arbitrary streams
* :class:`StderrHandler` for logging to stderr
* :class:`FileHandler`, :class:`RotatingFileHandler` and
  :class:`TimedRotatingFileHandler` for logging to files
* :class:`MailHandler` for logging via e-mail
* :class:`SyslogHandler` for logging to the syslog daemon
* :class:`NTEventLogHandler` for logging to the Windows NT event log

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

Additionally it is still logged to stderr.  If you don't want handled log
records to go to the next handler (and in this case the global handler) you can
disable this by setting *bubble* to False::

    from logbook import FileHandler

    error_handler = FileHandler('errors.log', level='ERROR')
    with error_handler.applicationbound(bubble=False):
        # whatever is executed here and an error is logged to the
        # error handler but it will not bubble up to the default
        # stderr handler.
        ...
