Welcome to Logbook
==================

Logbook is a logging system for Python that replaces the standard library's
logging module.  It was designed with both complex and simple applications
in mind and the idea to make logging fun:

>>> from logbook import Logger, StreamHandler
>>> import sys
>>> StreamHandler(sys.stdout).push_application()
>>> log = Logger('Logbook')
>>> log.info('Hello, World!')
[2015-10-05 18:55:56.937141] INFO: Logbook: Hello, World!

What makes it fun?  What about getting log messages on your phone or
desktop notification system?  :ref:`Logbook can do that <notifiers>`.

Feedback is appreciated.  The docs here only show a tiny,
tiny feature set and can be incomplete. We will have better docs
soon, but until then we hope this gives a sneak peek about how cool
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
   cookbook
   changelog

Project Information
-------------------

.. cssclass:: toctree-l1

* `Download from PyPI`_
* `GitHub repository`_
* `Mailing list`_

.. _Download from PyPI: https://pypi.org/project/Logbook
.. _GitHub repository: https://github.com/getlogbook/logbook
.. _Mailing list: https://groups.google.com/g/pocoo-libs
