API
===

.. module:: logbook


Logger Interface
----------------

.. autoclass:: Logger
   :members:
   :inherited-members:

.. autoclass:: LoggerGroup
   :members:

.. autoclass:: LogRecord
   :members:

.. autofunction:: get_level_name

.. autofunction:: lookup_level

.. data:: CRITICAL
          ERROR
          WARNING
          INFO
          DEBUG
          NOTSET

   The log level constants


Processor Interface
-------------------

.. autoclass:: Processor
   :members:
   :inherited-members:

Handler Base Interface
----------------------

.. autoclass:: Handler
   :members:
   :inherited-members:

.. autoclass:: NestedSetup
   :members:

.. autoclass:: StringFormatter
   :members:

Utility Functions
-----------------

.. autofunction:: debug

.. autofunction:: info

.. autofunction:: warn

.. autofunction:: warning

.. autofunction:: notice

.. autofunction:: error

.. autofunction:: exception

.. autofunction:: catch_exceptions

.. autofunction:: critical

.. autofunction:: log

Core Handlers
-------------

.. autoclass:: StreamHandler
   :members:

.. autoclass:: FileHandler
   :members:

.. autoclass:: StderrHandler
   :members:

.. autoclass:: RotatingFileHandler
   :members:

.. autoclass:: TimedRotatingFileHandler
   :members:

.. autoclass:: TestHandler
   :members:

.. autoclass:: MailHandler
   :members:

.. autoclass:: SyslogHandler
   :members:

.. autoclass:: NTEventLogHandler
   :members:

.. autoclass:: NullHandler
   :members:

.. autofunction:: create_syshandler


The More Module
---------------

.. module:: logbook.more

.. autoclass:: TaggingLogger
   :members:
   :inherited-members:

.. autoclass:: TaggingHandler
   :members:

.. autoclass:: FingersCrossedHandler
   :members:

.. autoclass:: MultiProcessingHandler
   :members:

.. autoclass:: GrowlHandler
   :members:

.. autoclass:: TwitterHandler
   :members:

.. autoclass:: JinjaFormatter
   :members:


Queue Support
-------------

.. module:: logbook.queues

.. autoclass:: ZeroMQHandler
   :members:

.. autoclass:: ZeroMQSubscriber
   :members:

.. autoclass:: ZeroMQThreadController
   :members:


Ticketing Support
-----------------

.. module:: logbook.ticketing

.. autoclass:: TicketingBaseHandler
   :members:

.. autoclass:: TicketingHandler
   :members:

.. autoclass:: BackendBase
   :members:

.. autoclass:: SQLAlchemyBackend

.. autoclass:: MongoDBBackend


Logging Compatibility
---------------------

.. module:: logbook.compat

.. autofunction:: redirect_logging

.. autofunction:: redirected_logging

.. autoclass:: RedirectLoggingHandler
   :members:


Warnings Compatibility
----------------------

.. currentmodule:: logbook.compat

.. autofunction:: redirect_warnings

.. autofunction:: redirected_warnings


Internal API
------------

.. module:: logbook.base

.. autofunction:: dispatch_record

.. autoclass:: StackedObject
   :members:

.. autoclass:: RecordDispatcher
   :members:

.. autoclass:: LoggerMixin
   :members:

.. module:: logbook.handlers

.. autoclass:: RotatingFileHandlerBase
   :members:

.. autoclass:: StringFormatterHandlerMixin
   :members:
