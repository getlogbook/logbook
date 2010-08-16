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

.. autoclass:: JinjaFormatter
   :members:


Logging Compatibility
---------------------

.. module:: logbook.compat

.. autofunction:: redirect_logging

.. autofunction:: temporarily_redirected_logging

.. autoclass:: RedirectLoggingHandler
   :members:


Internal API
------------

.. module:: logbook.base

.. autoclass:: RecordDispatcher
   :members:

.. autoclass:: LoggerMixin
   :members:

.. module:: logbook.handlers

.. autoclass:: RotatingFileHandlerBase
   :members:

.. autoclass:: StringFormatterHandlerMixin
   :members:
