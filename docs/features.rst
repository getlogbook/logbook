Why you should use Logbook
==========================

Although the Python standard library provides a logging system, you should use
Logbook.  Currently logbook is an alpha version and should be considered a
developer preview.  Because it was prototyped in a couple of days, it leverages
some features of Python that are not available in older Python releases.
Logbook requires Python 2.5 or higher and does not yet support Python 3
but support is upcoming.

Core Features
-------------

-   Logbook is based on the concept of loggers that are extensible by the
    application.
-   Each logger and handler, as well as other parts of the system, may inject
    additional information into the logging record that improves the usefulness
    of log entries.
-   Handlers can be set on an application-wide stack as well as a thread-wide
    stack.  Setting a handler does not replace existing handlers, but gives it
    higher priority.  Each handler has the ability to prevent records from
    propagating to lower-priority handlers.
-   Logbook comes with a useful default configuration that spits all the
    information to stderr in a useful manner.
-   All of the built-in handlers have a useful default configuration applied with
    formatters that provide all the available information in a format that
    makes the most sense for the given handler.  For example, a default stream
    handler will try to put all the required information into one line, whereas
    an email handler will split it up into nicely formatted ASCII tables that
    span multiple lines.
-   Logbook has built-in handlers for streams, arbitrary files, files with time
    and size based rotation, a handler that delivers mails, a handler for the
    syslog daemon as well as the NT log file.
-   There is also a special "fingers crossed" handler that, in combination with
    the handler stack, has the ability to accumulate all logging messages and
    will deliver those in case a severity level was exceeded.  For example, it
    can withhold all logging messages for a specific request to a web
    application until an error record appears, in which case it will also send
    all withheld records to the handler it wraps.  This way, you can always log
    lots of debugging records, but only get see them when they can actually
    tell you something of interest.
-   It is possible to inject a handler for testing that records messages for
    assertions.
-   Logbook was designed to be fast and with modern Python features in mind.
    For example, it uses context managers to handle the stack of handlers as
    well as new-style string formatting for all of the core log calls.
-   Builtin support for ZeroMQ and other means to distribute log messages
    between heavily distributed systems and multiple processes.
-   The Logbook system does not depend on log levels.  In fact, custom log
    levels are not supported, instead we strongly recommend using logging
    subclasses or log processors that inject tagged information into the log
    record for this purpose.

Advantages over Logging
-----------------------

If properly configured, Logbook's logging calls will be very cheap and
provide a great performance improvement over the standard library's
logging module.  While we are not there yet, there will be some
performance improvements in the upcoming versions when we implement
certain critical code paths in C.

It also supports the ability to inject additional information for all
logging calls happening in a specific thread.  For example, this makes it
possible for a web application to add request-specific information to each
log record such as remote address, request URL, HTTP method and more.

The logging system is (besides the stack) stateless and unit testing it is
very simple.  If context managers are used, it is impossible to corrupt
the stack, so each test can easily hook in custom log handlers.

It should be Fun
----------------

Logging should be fun.  A good log setup makes debugging easier when
things go rough.  For good results you really have to start using logging
before things actually break.  Logbook comes with a couple of unusual log
handlers to bring the fun back to logging.  You can log to your personal
twitter feed, you can log to mobile devices, your desktop notification
system and more.

Logbook in a Nutshell
---------------------

This is how easy it is to get started with Logbook::

    from logbook import warn
    warn('This is a warning')

That will use the default logging channel.  But you can create as many as
you like::

    from logbook import Logger
    log = Logger('My Logger')
    log.warn('This is a warning')

Roadmap
-------

Here a list of things you can expect in upcoming versions:

-   c implementation of the internal stack management and record
    dispatching for higher performance.
-   a ticketing log handler that creates tickets in trac and redmine.
-   a web frontend for the ticketing database handler.
