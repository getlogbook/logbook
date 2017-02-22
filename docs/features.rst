What does it do?
================

Although the Python standard library provides a logging system, you should
consider having a look at Logbook for your applications.

We think it will work out for you and be fun to use :)

Logbook leverages some features of Python that are not available in older Python releases.
Logbook currently requires Python 2.7 or higher including Python 3 (3.3 or
higher, 3.2 and lower is not supported).

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
-   Logbook comes with a quick optional configuration that spits all the
    information to stderr in a useful manner (by setting the LOGBOOK_INSTALL_DEFAULT_HANDLER
    environment variable). This is useful for webapps, for example.
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
-   Builtin support for ZeroMQ, RabbitMQ, Redis and other means to distribute
    log messages between heavily distributed systems and multiple processes.
-   The Logbook system does not depend on log levels.  In fact, custom log
    levels are not supported, instead we strongly recommend using logging
    subclasses or log processors that inject tagged information into the log
    record for this purpose.
-   :pep:`8` naming and code style.

Advantages over Logging
-----------------------

If properly configured, Logbook's logging calls will be very cheap and
provide a great performance improvement over an equivalent configuration
of the standard library's logging module.  While for some parts we are not
quite at performance we desire, there will be some further performance
improvements in the upcoming versions.

It also supports the ability to inject additional information for all
logging calls happening in a specific thread or for the whole application.
For example, this makes it possible for a web application to add
request-specific information to each log record such as remote address,
request URL, HTTP method and more.

The logging system is (besides the stack) stateless and makes unit testing
it very simple.  If context managers are used, it is impossible to corrupt
the stack, so each test can easily hook in custom log handlers.

Cooperation
-----------

Logbook is an addon library to Python and working in an area where there
are already a couple of contestants.  First of all there is the standard
library's :mod:`logging` module, secondly there is also the
:mod:`warnings` module which is used internally in Python to warn about
invalid uses of APIs and more.  We know that there are many situations
where you want to use either of them.  Be it that they are integrated into
a legacy system, part of a library outside of your control or just because
they are a better choice.

Because of that, Logbook is two-way compatible with :mod:`logging` and
one-way compatible with :mod:`warnings`.  If you want, you can let all
logging calls redirect to the logbook handlers or the other way round,
depending on what your desired setup looks like.  That way you can enjoy
the best of both worlds.

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

    from logbook import warn, StreamHandler
    import sys
    StreamHandler(sys.stdout).push_application()
    warn('This is a warning')

Roadmap
-------

Here a list of things you can expect in upcoming versions:

-   c implementation of the internal stack management and record
    dispatching for higher performance.
-   a ticketing log handler that creates tickets in trac and redmine.
-   a web frontend for the ticketing database handler.
