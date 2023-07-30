Handlers
========

This documents the base handler interface as well as the provided core
handlers.  There are additional handlers for special purposes in the
:mod:`logbook.more`, :mod:`logbook.ticketing` and :mod:`logbook.queues`
modules.

.. currentmodule:: logbook

Base Interface
--------------

.. autoclass:: Handler
   :members:
   :inherited-members:

.. autoclass:: NestedSetup
   :members:

.. autoclass:: StringFormatter
   :members:

Core Handlers
-------------

.. autoclass:: StreamHandler
   :members:

.. autoclass:: FileHandler
   :members:

.. autoclass:: MonitoringFileHandler
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

.. autoclass:: GMailHandler
   :members:

.. autoclass:: SyslogHandler
   :members:

.. autoclass:: NTEventLogHandler
   :members:

.. autoclass:: NullHandler
   :members:

.. autoclass:: WrapperHandler
   :members:

.. autofunction:: create_syshandler

Special Handlers
----------------

.. autoclass:: FingersCrossedHandler
   :members:

.. autoclass:: GroupHandler
   :members:

Mixin Classes
-------------

.. autoclass:: StringFormatterHandlerMixin
   :members:

.. autoclass:: HashingHandlerMixin
   :members:

.. autoclass:: LimitingHandlerMixin
   :members:
