The More Module
===============

The more module implements special handlers and other things that are
beyond the scope of Logbook itself or depend on external libraries.
Additionally there are some handlers in :mod:`logbook.ticketing` and
:mod:`logbook.queues`.

.. module:: logbook.more

Tagged Logging
--------------

.. autoclass:: TaggingLogger
   :members:
   :inherited-members:

.. autoclass:: TaggingHandler
   :members:

Special Handlers
----------------

.. autoclass:: FingersCrossedHandler
   :members:

.. autoclass:: GrowlHandler
   :members:

.. autoclass:: TwitterHandler
   :members:

Other
-----

.. autoclass:: JinjaFormatter
   :members:
