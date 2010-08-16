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


Handler Base Interface
----------------------

.. autoclass:: Handler
   :members:

.. autoclass:: NestedHandlerSetup
   :members:

.. autoclass:: StringFormatter
   :members:

.. autofunction:: iter_context_handlers

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


Internal API
------------

.. autoclass:: logbook.base.RecordDispatcher
   :members:

.. autoclass:: logbook.base.LoggerMixin
   :members:

.. autoclass:: logbook.handlers.RotatingFileHandlerBase
   :members:
