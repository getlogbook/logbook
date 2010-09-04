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
