# -*- coding: utf-8 -*-
"""
    logbook.testsuite
    ~~~~~~~~~~~~~~~~~

    The logbook testsuite.

    :copyright: (c) 2010 by Armin Ronacher, Georg Brandl.
    :license: BSD, see LICENSE for more details.
"""
import sys
import platform

if platform.python_version() < "2.7":
    import unittest2 as unittest
else:
    import unittest
import logbook
import six

_missing = object()

require_py3 = unittest.skipUnless(six.PY3, "Requires Python 3")
def require_module(module_name):
    try:
        __import__(module_name)
    except ImportError:
        return unittest.skip("Requires the %r module" % (module_name,))
    return lambda func: func

class LogbookTestSuite(unittest.TestSuite):
    pass

class LogbookTestCase(unittest.TestCase):

    def setUp(self):
        self.log = logbook.Logger('testlogger')

# silence deprecation warning displayed on Py 3.2
LogbookTestCase.assert_ = LogbookTestCase.assertTrue

def make_fake_mail_handler(**kwargs):
    class FakeMailHandler(logbook.MailHandler):
        mails = []

        def get_connection(self):
            return self

        def close_connection(self, con):
            pass

        def sendmail(self, fromaddr, recipients, mail):
            self.mails.append((fromaddr, recipients, mail))

    kwargs.setdefault('level', logbook.ERROR)
    return FakeMailHandler('foo@example.com', ['bar@example.com'], **kwargs)


def missing(name):
    def decorate(f):
        def wrapper(*args, **kwargs):
            old = sys.modules.get(name, _missing)
            sys.modules[name] = None
            try:
                f(*args, **kwargs)
            finally:
                if old is _missing:
                    del sys.modules[name]
                else:
                    sys.modules[name] = old
        return wrapper
    return decorate


def suite():
    loader = unittest.TestLoader()
    suite = LogbookTestSuite()
    suite.addTests(loader.loadTestsFromName('logbook.testsuite.test_regular'))
    if sys.version_info >= (2, 5):
        suite.addTests(loader.loadTestsFromName
                       ('logbook.testsuite.test_contextmanager'))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
