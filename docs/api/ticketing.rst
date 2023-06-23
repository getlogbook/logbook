Ticketing Support
=================

This documents the support classes for ticketing.  With ticketing handlers
log records are categorized by location and for every emitted log record a
count is added.  That way you know how often certain messages are
triggered, at what times and when the last occurrence was.

.. currentmodule:: logbook.ticketing

.. autoclass:: TicketingBaseHandler
   :members:

.. autoclass:: TicketingHandler
   :members:

.. autoclass:: BackendBase
   :members:

.. autoclass:: SQLAlchemyBackend

.. autoclass:: MongoDBBackend
