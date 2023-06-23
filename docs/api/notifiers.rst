.. _notifiers:

The Notifiers Module
====================

The notifiers module implements special handlers for various platforms
that depend on external libraries.
The more module implements special handlers and other things that are
beyond the scope of Logbook itself or depend on external libraries.

.. currentmodule:: logbook.notifiers

.. autofunction:: create_notification_handler

OSX Specific Handlers
---------------------

.. autoclass:: GrowlHandler
   :members:

Linux Specific Handlers
-----------------------

.. autoclass:: LibNotifyHandler
   :members:

Other Services
--------------

.. autoclass:: BoxcarHandler
   :members:

.. autoclass:: NotifoHandler
  :members:

.. autoclass:: PushoverHandler
  :members:

Base Interface
--------------

.. autoclass:: NotificationBaseHandler
   :members:
