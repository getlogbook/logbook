Core Interface
==============

This implements the core interface.

.. currentmodule:: logbook

.. autoclass:: Logger
   :members:
   :inherited-members:

.. autoclass:: LoggerGroup
   :members:

See :ref:`common-formatting-fields` for examples of record attributes in output
format strings.

.. autoclass:: LogRecord
   :members:

.. autoclass:: Flags
   :members:
   :inherited-members:

.. autoclass:: Processor
   :members:
   :inherited-members:

.. autofunction:: get_level_name

.. autofunction:: lookup_level

.. data:: CRITICAL
          ERROR
          WARNING
          INFO
          DEBUG
          NOTSET

   The log level constants
