Unittesting Support
===================

.. currentmodule:: logbook

Logbook has builtin support for testing logging calls.  There is a handler
that can be hooked in and will catch all log records for inspection.  Not
only that, it also provides methods to test if certain things were logged.

Basic Setup
-----------

The interface to satisfaction is :class:`logbook.TestHandler`.  Create it,
and bind it, and you're done.  If you are using classic :mod:`unittest`
test cases, you might want to set it up in the before and after callback
methods::

    import logbook
    import unittest

    class LoggingTestCase(unittest.TestCase):

        def setUp(self):
            self.log_handler = logbook.TestHandler()
            self.log_handler.push_thread()

        def tearDown(self):
            self.log_handler.pop_thread()

Alternatively you can also use it in a with statement in an individual
test.  This is also how this can work in nose and other testing systems::

    def my_test():
        with logbook.TestHandler() as log_handler:
            ...


Test Handler Interface
----------------------

The test handler has a few attributes and methods to gain access to the
logged messages.  The most important ones are :attr:`~TestHandler.records`
and :attr:`~TestHandler.formatted_records`.  The first is a list of the
captured :class:`~LogRecord`\s, the second a list of the formatted records
as unicode strings:

>>> from logbook import TestHandler, Logger
>>> logger = Logger('Testing')
>>> handler = TestHandler()
>>> handler.push_thread()
>>> logger.warn('Hello World')
>>> handler.records
[<logbook.base.LogRecord object at 0x100640cd0>]
>>> handler.formatted_records
[u'[WARNING] Testing: Hello World']


.. _probe-log-records:

Probe Log Records
-----------------

The handler also provide some convenience methods to do assertions:

>>> handler.has_warnings
True
>>> handler.has_errors
False
>>> handler.has_warning('Hello World')
True

Methods like :meth:`~logbook.TestHandler.has_warning` accept two
arguments:

`message`
    If provided and not `None` it will check if there is at least one log
    record where the message matches. This can also be a compiled regular
    expression.

`channel`
    If provided and not `None` it will check if there is at least one log
    record where the logger name of the record matches.

Example usage:

>>> handler.has_warning('A different message')
False
>>> handler.has_warning(re.compile('^Hello'))
True
>>> handler.has_warning('Hello World', channel='Testing')
True
>>> handler.has_warning(channel='Testing')
True
