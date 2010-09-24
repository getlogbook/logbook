# -*- coding: utf-8 -*-
"""
    logbook.testsuite
    ~~~~~~~~~~~~~~~~~

    The logbook testsuite.

    :copyright: (c) 2010 by Armin Ronacher, Georg Brandl.
    :license: BSD, see LICENSE for more details.
"""
import sys
import unittest
import logbook


_skipped_modules = []
_missing = object()
_func_ident = lambda f: f
_func_none = lambda f: None


class LogbookTestSuite(unittest.TestSuite):

    def run(self, result):
        try:
            return unittest.TestSuite.run(self, result)
        finally:
            sys.stderr.write('\n')
            for mod in _skipped_modules:
                msg = '*** Failed to import %s, tests skipped.\n' % mod
                sys.stderr.write(msg)


class LogbookTestCase(unittest.TestCase):

    def setUp(self):
        self.log = logbook.Logger('testlogger')


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


def skip_if(condition):
    if condition:
        return _func_ident
    else:
        return _func_none


def require(name):
    if name in _skipped_modules:
        return _func_none
    try:
        __import__(name)
    except ImportError:
        _skipped_modules.append(name)
        return _func_none
    return _func_ident


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
