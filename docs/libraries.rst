Logbook in Libraries
====================

Logging becomes more useful the higher the number of components in a
system that are using it.  Logbook itself is not a widely supported
library so far, but a handful of libraries are using the :mod:`logging`
already which can be redirected to Logbook if necessary.

Logbook itself is easier to support for libraries than logging because it
does away with the central logger registry and can easily be mocked in
case the library is not available.

Mocking Logbook
---------------

If you want to support Logbook in your library but not depend on it you
can copy/paste the following piece of code.  It will attempt to import
logbook and create a :class:`~logbook.Logger` and if it fails provide a
class that just swallows all calls::

    try:
        from logbook import Logger
    except ImportError:
        class Logger(object):
            def __init__(self, name, level=0):
                self.name = name
                self.level = level
            debug = info = warn = warning = notice = error = exception = \
                critical = log = lambda *a, **kw: None

    log = Logger('My library')

Best Practices
--------------

-   A library that wants to log to the Logbook system should generally be
    designed to provide an interface to the record dispatchers it is
    using.  That does not have to be a reference to the record dispatcher
    itself, it is perfectly fine if there is a toggle to switch it on or
    off.

-   The channel name should be readable and descriptive.

-   For example, if you are a database library that wants to use the
    logging system to log all SQL statements issued in debug mode, you can
    enable and disable your record dispatcher based on that debug flag.

-   Libraries should never set up log setups except temporarily on a
    per-thread basis if it never changes the stack for a longer duration
    than a function call in a library.  For example, hooking in a null
    handler for a call to a noisy function is fine, changing the global
    stack in a function and not reverting it at the end of the function is
    bad.

Example Setup
-------------

Consider how your logger should be configured by default. Users familiar with
:mod:`logging` from the standard library probably expect your logger to be
disabled by default::

    import yourmodule
    import logbook

    yourmodule.logger.enable()

    def main():
        ...
        yourmodule.something()
        ...

    if __name__ == '__main__':
        with logbook.StderrHandler():
            main()

or set to a high level (e.g. `WARNING`) by default, allowing them to opt in to
more detail if desired::

    import yourmodule
    import logbook

    yourmodule.logger.level = logbook.WARNING

    def main():
        ...
        yourmodule.something()
        ...

    if __name__ == '__main__':
        with logbook.StderrHandler():
            main()

Either way, make sure to document how your users can enable your logger,
including basic use of logbook handlers. Some users may want to continue using
:mod:`logging`, so you may want to link to
:class:`~logbook.compat.LoggingHandler`.

Multiple Logger Example Setup
-----------------------------

You may want to use multiple loggers in your library. It may be worthwhile to
add a logger group to allow the level or disabled attributes of all your
loggers to be set at once.

For example, your library might look something like this:

.. code-block:: python
   :caption: yourmodule/__init__.py

    from .log import logger_group

.. code-block:: python
    :caption: yourmodule/log.py

    import logbook

    logger_group = logbook.LoggerGroup()
    logger_group.level = logbook.WARNING

.. code-block:: python
    :caption: yourmodule/engine.py

    from logbook import Logger
    from .log import logger_group

    logger = Logger('yourmodule.engine')
    logger_group.add_logger(logger)

.. code-block:: python
    :caption: yourmodule/parser.py

    from logbook import Logger
    from .log import logger_group

    logger = Logger('yourmodule.parser')
    logger_group.add_logger(logger)

The library user can then choose what level of logging they would like from
your library::

    import logbook
    import yourmodule

    yourmodule.logger_group.level = logbook.INFO

They might only want to see debug messages from one of the loggers::

    import logbook
    import yourmodule

    yourmodule.engine.logger.level = logbook.DEBUG

Debug Loggers
-------------

Sometimes you want to have loggers in place that are only really good for
debugging.  For example you might have a library that does a lot of
server/client communication and for debugging purposes it would be nice if
you can enable/disable that log output as necessary.

In that case it makes sense to create a logger and disable that by default
and give people a way to get hold of the logger to flip the flag.
Additionally you can override the :attr:`~logbook.Logger.disabled` flag to
automatically set it based on another value::

    class MyLogger(Logger):
        @property
        def disabled(self):
            return not database_connection.debug
    database_connection.logger = MyLogger('mylibrary.dbconnection')
