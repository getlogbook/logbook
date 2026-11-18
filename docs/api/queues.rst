Queue Support
=============

The queue support module makes it possible to add log records to a queue
system.  This is useful for distributed setups where you want multiple
processes to log to the same backend.

.. module:: logbook.queues

ZeroMQ
------

:class:`ZeroMQHandler` and :class:`ZeroMQSubscriber` must use the same
``multi``:

===================  =========================  =========================
``multi``            :class:`ZeroMQHandler`     :class:`ZeroMQSubscriber`
===================  =========================  =========================
``False`` (default)  binds a `PUB`_ socket      connects a `SUB`_ socket
``True``             connects a `PUSH`_ socket  binds a `PULL`_ socket
===================  =========================  =========================

.. _PUB: https://zeromq.org/socket-api/#pub-socket
.. _SUB: https://zeromq.org/socket-api/#sub-socket
.. _PUSH: https://zeromq.org/socket-api/#push-socket
.. _PULL: https://zeromq.org/socket-api/#pull-socket

.. autoclass:: ZeroMQHandler
   :members:

.. autoclass:: ZeroMQSubscriber
   :members:
   :inherited-members:

Redis
-----

.. autoclass:: RedisHandler
   :members:

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

Execnet
-------

.. autoclass:: ExecnetChannelHandler
   :members:

.. autoclass:: ExecnetChannelSubscriber
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
