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
level as an argument.

Each call to a logging method creates a log *record* which is then passed to
*handlers*, which decide how to store or present the logging info.
