Queue Support
=============

The queue support module makes it possible to add log records to a queue
system.  This is useful for distributed setups where you want multiple
processes to log to the same backend.  Currently supported are ZeroMQ as
well as the :mod:`multiprocessing` :class:`~multiprocessing.Queue` class.

.. currentmodule:: logbook.queues

ZeroMQ
------

.. autoclass:: ZeroMQHandler
   :members:

.. autoclass:: ZeroMQSubscriber
   :members:
   :inherited-members:

AMQP Message Queues
-------------------

.. autoclass:: MessageQueueHandler
    :members:

.. autoclass:: MessageQueueSubscriber
    :members:

MultiProcessing
---------------

.. autoclass:: MultiProcessingHandler
   :members:

.. autoclass:: MultiProcessingSubscriber
   :members:
   :inherited-members:

Other
-----

.. autoclass:: ThreadedWrapperHandler
   :members:

.. autoclass:: SubscriberGroup
   :members:

Base Interface
--------------

.. autoclass:: SubscriberBase
   :members:

.. autoclass:: ThreadController
   :members:

.. autoclass:: TWHThreadController
   :members:
