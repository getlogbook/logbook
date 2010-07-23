Quickstart
==========

Logbook makes it very easy to get started with logging.  Just import the
logger class, create yourself a logger and you are set:

>>> from logbook import Logger
>>> log = Logger('My Awesome Logger')
>>> log.warn('This is too cool for stdlib')
[2010-07-23 16:34] WARNING: My Awesome Logger: This is too cool for stdlib
