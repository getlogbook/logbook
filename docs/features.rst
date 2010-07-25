Why you should use Logbook
==========================

Although the Python standard library provides a logging system, you should
use Logbook if this is possible for you.  Currently logbook is an alpha
version and should be considered as a developer preview.  Because it was
prototyped in a couple of days it leverages some features of Python that
are not available in older Python builds.  Currently Logbook only supports
Python 2.6 and 2.7, with upcoming support for Python 3.

Core Features
-------------

-   Logbook is based on the concept of loggers that are extensible by the
    application.
-   Each logger and handler, as well as other parts of the system may
    inject additional information into the logging record that improves
    the usefulnes of log entries.
-   handlers can be set on an application wide stack as well as a thread
    wide stack.  Setting a handler does not replace an existing handler
    but gives it higher priority.  Each handler has the ability to bubble
    up the information to the lower handler or to stop propagating the
    record.
-   Logbook comes with a useful default configuration taht spits all the
    information to stderr in a useful manner.
-   All the builtin handlers have a useful default configuration applied
    with formatters that provide all the available information in a format
    that makes most sense for the given handler.  For example a default
    stream handler will try to put all the required information into one
    line whereas an email handler will split it up into properly formatted
    ASCII tables that spawn multiple lines
-   Logbook has builtin handlers for streams, arbitrary files, files with
    time and size based rotation, a handler that delivers mails, a handler
    for the syslog daemon as well as the NT log file as well as a
    special fingers crossed handler that in combination with the handler
    stack has the ability to accumulate all logging messages and will
    deliver those in case a severity level was exceeded.  For example it
    can log all logging messages until the first error record appered in
    which case it will send everything to handler it wraps.  Last but not
    least it is possible to inject a handler for testing that records
    messages for assertions.
-   Logbook was designed to be fast and with modern Python features in
    mind.  For example it uses context managers to handle the stack of
    handlers as well as new-style string formatting for all of the core
    log calls.
-   The Logbook system does not depend on log levels.  In fact, custom
    log levels are not supported, instead we strongly recommend using
    logging subclasses or log processors that inject tagged information
    into the log record for this purpose.

Advantages over Logging
-----------------------

If properly configured, Logbook's logging calls will be very cheap and
give a great performance improvement over the standard library's logging
module.

It also supports the ability to inject additional information for all
logging calls happening in a specific thread.  For example, this makes it
possible for a web application to add request-specific information to each
log record such as remote address, request URL, HTTP method and more.

The logging system is (besides the stack) stateless and makes it
unittesting very simple.  If context managers are used it is impossible to
corrupt the stack so each test can easily hook in custom log handlers.

Logbook in a Nutshell
---------------------

This is how easy it is to get started with Logbook::

    from logbook import Logger

    log = Logger('My Logger')
    log.warn('This is a warning')
