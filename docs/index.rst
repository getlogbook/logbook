Welcome to Logbook
==================

Logbook is a logging system for Python that replaces the standard library's
logging module.  It was designed with both complex and simple applications
in mind and the idea to make logging fun:

>>> from logbook import Logger
>>> log = Logger('Logbook')
>>> log.info('Hello, World!')
[2010-07-23 16:34] INFO: Logbook: Hello, World!

What makes it fun?  What about getting log messages on your phone or
desktop notification system?  :ref:`Logbook can do that <notifiers>`.

Feedback is appreciated.  The docs here only show a tiny,
tiny feature set and can be incomplete. We will have better docs
soon, but until then we hope this gives a sneak peak about how cool
Logbook is.  If you want more, have a look at the comprehensive suite of tests.

Documentation
-------------

.. toctree::
   :maxdepth: 2

   features
   quickstart
   setups
   stacks
   performance
   libraries
   unittesting
   ticketing
   compat
   api/index
   designexplained
   designdefense
   changelog

Project Information
-------------------

.. cssclass:: toctree-l1

* `Download from PyPI`_
* `Master repository on GitHub`_
* `Mailing list`_
* IRC: ``#pocoo`` on freenode

.. _Download from PyPI: http://pypi.python.org/pypi/Logbook
.. _Master repository on GitHub: https://github.com/mitsuhiko/logbook
.. _Mailing list: http://groups.google.com/group/pocoo-libs
