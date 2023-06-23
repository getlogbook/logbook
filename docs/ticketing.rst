Logging to Tickets
==================

Logbook supports the concept of creating unique tickets for log records
and keeping track of the number of times these log records were created.
The default implementation logs into a relational database, but there is a
baseclass that can be subclassed to log into existing ticketing systems
such as trac or other data stores.

The ticketing handlers and store backends are all implemented in the
module :mod:`logbook.ticketing`.

How does it work?
-----------------

When a ticketing handler is used each call to a logbook logger is assigned
a unique hash that is based on the name of the logger, the location of the
call as well as the level of the message.  The message itself is not taken
into account as it might be changing depending on the arguments passed to
it.

Once that unique hash is created the database is checked if there is
already a ticket for that hash.  If there is, a new occurrence is logged
with all details available.  Otherwise a new ticket is created.

This makes it possible to analyze how often certain log messages are
triggered and over what period of time.

Why should I use it?
--------------------

The ticketing handlers have the big advantage over a regular log handler
that they will capture the full data of the log record in machine
processable format.  Whatever information was attached to the log record
will be send straight to the data store in JSON.

This makes it easier to track down issues that might happen in production
systems.  Due to the higher overhead of ticketing logging over a standard
logfile or something comparable it should only be used for higher log
levels (:data:`~logbook.WARNING` or higher).

Common Setups
-------------

The builtin ticketing handler is called
:class:`~logbook.ticketing.TicketingHandler`.  In the default configuration
it will connect to a relational database with the help of `SQLAlchemy`_
and log into two tables there: tickets go into ``${prefix}tickets`` and
occurrences go into ``${prefix}occurrences``.  The default table prefix is
``'logbook_'`` but can be overridden.  If the tables do not exist already,
the handler will create them.

Here an example setup that logs into a postgres database::

    from logbook import ERROR
    from logbook.ticketing import TicketingHandler
    handler = TicketingHandler('postgres://localhost/database',
                                       level=ERROR)
    with handler:
        # everything in this block and thread will be handled by
        # the ticketing database handler
        ...

Alternative backends can be swapped in by providing the `backend`
parameter.  There is a second implementation of a backend that is using
MongoDB: :class:`~logbook.ticketing.MongoDBBackend`.

.. _SQLAlchemy: https://www.sqlalchemy.org/
