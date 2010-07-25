Quickstart
==========

.. currentmodule:: logbook

Logbook makes it very easy to get started with logging.  Just import the
logger class, create yourself a logger and you are set:

>>> from logbook import Logger
>>> log = Logger('My Awesome Logger')
>>> log.warn('This is too cool for stdlib')
[2010-07-23 16:34] WARNING: My Awesome Logger: This is too cool for stdlib

The basic interface is similar to what you may already know from the standard
library's :mod:`logging` module.

There are several logging levels, available as methods on the logger:

* ``critical`` -- for errors that lead to termination
* ``error`` -- for errors that occur
* ``warning`` -- for exceptional circumstances that might not be errors
* ``notice`` -- for non-error messages you usually want to see
* ``info`` -- for messages you usually don't want to see
* ``debug`` -- for debug messages

Alternately, there is the :meth:`~Logger.log` method that takes the logging
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

So how are handlers registered?  If you are used to the standard Python
logging system it works a little bit different here.  Handlers can be
registered for a thread or for a whole process or individually for a
logger.  However it is strongly recommended not to add handlers to loggers
unless there is a very good use case for that.

If you want errors to go to syslog, you can set up logging like this::

    from logbook import FileHandler

    error_handler = FileHandler('errors.log', level='ERROR')
    with error_handler.applicationbound():
        # whatever is executed here and an error is logged to the
        # error handler
        ...

Additionally it is still logged to stderr.  If you don't want handled
log records to go to the next handler (and in this case the global
handler) you can disable this by setting bubble to False::

    from logbook import FileHandler

    error_handler = FileHandler('errors.log', level='ERROR')
    with error_handler.applicationbound(bubble=False):
        # whatever is executed here and an error is logged to the
        # error handler but it will not bubble up to the default
        # stderr handler.
        ...

Desktop Application Setup
-------------------------

If you are a desktop application (command line or GUI) you probably have a
line like this in your code::

    if __name__ == '__main__':
        main()

This is what you should wrap with a `with`-statement that sets up your log
handler::

    from logbook import FileHandler
    log_handler = FileHandler('application.log')

    if __name__ == '__main__':
        with log_handler.applicationbound():
            main()

Alternatively you can also just push a handler in there::

    from logbook import FileHandler
    log_handler = FileHandler('application.log')
    log_handler.push_application()

    if __name__ == '__main__':
        main()

Please keep in mind that you will have to pop the handlers in order if you
want to remove them from the stack, so it is recommended to use the with
statement there if you plan on reverting the handlers.

Web Application Setup
---------------------

Typical modern web applications written in Python have two separate
contexts where code might be executed: when the code is imported, as well
as when a request is handled.  The first case is easy to handle, just push
a global file handler that writes everything into a file.

But Logbook gives you also the ability to improve upon the logging.  For
example you can easily create yourself a log handler that is used for
request-bound logging that also injects additional information.

For this you can either subclass the logger or you can bind to the handler
with a function that is invoked before logging.  The latter has the
advantage that it will also be triggered for other logger instances which
might be used by a different library.

Here a simple WSGI example application that showcases sending error mails
for errors happened during a WSGI application::

    from logbook import MailHandler

    mail_handler = MailHandler('errors@example.com',
                               ['admin@example.com'],
                               format_string=u'''\
    Subject: Application Error at {request.extra[url]}

    Message type:       {record.level_name}
    Location:           {record.filename}:{record.lineno}
    Module:             {record.module}
    Function:           {record.func_name}
    Time:               {record.time:%Y-%m-%d %H:%M:%S}
    Remote IP:          {record.extra[ip]}
    Request:            {record.extra[url]} [{request.extra[method]}]

    Message:

    {record.message}
    ''')

    def application(environ, start_response):
        req = Request(environ)

        def inject_info(record, handler):
            record.extra.update(
                ip=request.remote_addr,
                method=request.method,
                url=request.url
            )

        with mail_handler.threadbound(processor=inject_info):
            # standard WSGI processing happens here.  If an error
            # is logged, a mail will be sent to the admin on
            # example.com
            ...

Deeply Nested Setups
--------------------

If you want deeply nested logger setups, you can use the
:class:`NestedHandlerSetup` class which simplifies that.  This is best
explained with an example::

    from logbook import NestedHandlerSetup, NullHandler, FileHandler, \
         MailHandler

    # a nested handler setup can be used to configure more complex setups
    handlers = logbook.NestedHandlerSetup()

    # make sure we never bubble up to the stderr handler
    # if we run out of handlers handling
    handlers.add(NullHandler(), bubble=False)

    # then let messages that are at least warnings to to a logfile
    handlers.add(FileHandler('application.log', level='WARNING'))

    # errors should then be delivered by mail and also be kept
    # in the application log, so we let them bubble up.
    handlers.add(MailHandler('servererrors@example.com',
                             ['admin@example.com'],
                             level='ERROR'))

The :meth:`~logbook.NestedHandlerSetup.add` method accepts the same
arguments as :meth:`~logbook.Handler.applicationbound` and others.  Once
such a complex setup is defined, the nested handler setup can be used as
if it was a single handler::

    with handlers.contextbound():
        # everything here is handled as specified by the rules
        # above.
        ...
