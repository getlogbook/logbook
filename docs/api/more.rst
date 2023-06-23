The More Module
===============

The more module implements special handlers and other things that are
beyond the scope of Logbook itself or depend on external libraries.
Additionally there are some handlers in :mod:`logbook.ticketing`,
:mod:`logbook.queues` and :mod:`logbook.notifiers`.

.. currentmodule:: logbook.more

Tagged Logging
--------------

.. autoclass:: TaggingLogger
   :members:
   :inherited-members:

.. autoclass:: TaggingHandler
   :members:

Special Handlers
----------------

.. autoclass:: TwitterHandler
   :members:

.. autoclass:: SlackHandler
   :members:

.. autoclass:: ExternalApplicationHandler
   :members:

.. autoclass:: ExceptionHandler
   :members:

.. autoclass:: DedupHandler
   :members:

Colorized Handlers
------------------

.. versionadded:: 0.3

.. autoclass:: ColorizedStderrHandler

.. autoclass:: ColorizingStreamHandlerMixin
   :members:

Other
-----

.. autoclass:: JinjaFormatter
   :members:
