Welcome to Logbook
==================

Logbook is a logging sytem for Python that replaces the standard library's
logging module.  It was designed for complex and simple applications in mind.

>>> from logbook import Logger
>>> log = Logger('Logbook')
>>> log.info('Hello, World!')
[2010-07-23 16:34] INFO: Logbook: Hello, World!

This library is still under heavy development and the API is not fully finalized
yet.  Feedback is appreciated.  The docs here only show a tiny, tiny feature set
and are terribly incomplete.  We will have better docs soon, but until then we
hope this gives a sneak peak about how cool Logbook is.  If you want more, have
a look at the comprehensive `testsuite`_.

Documentation
-------------

.. toctree::
   :maxdepth: 1

   features
   quickstart
   compat

Project Information
-------------------

.. cssclass:: toctree-l1

* `Download from PyPI`_
* `Master repository on GitHub`_
* `Mailing list`_
* IRC: ``#pocoo`` on freenode


.. _testsuite: http://github.com/mitsuhiko/logbook/blob/master/test_logbook.py
.. _Download from PyPI: http://pypi.python.org/pypi/Logbook
.. _Master repository on GitHub: http://github.com/mitsuhiko/logbook
.. _Mailing list: http://groups.google.com/group/pocoo-libs
