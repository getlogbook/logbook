# -*- coding: utf-8 -*-
"""
    test utils for logbook
    ~~~~~~~~~~~~~~~~~~~~~~

    :copyright: (c) 2010 by Armin Ronacher, Georg Brandl.
    :license: BSD, see LICENSE for more details.
"""
from contextlib import contextmanager
import platform
import sys

if platform.python_version() < "2.7":
    import unittest2 as unittest
else:
    import unittest
import logbook
from logbook.helpers import StringIO

_missing = object()


def get_total_delta_seconds(delta):
    """
    Replacement for datetime.timedelta.total_seconds() for Python 2.5, 2.6 and 3.1
    """
    return (delta.microseconds + (delta.seconds + delta.days * 24 * 3600) * 10**6) / 10**6


require_py3 = unittest.skipUnless(sys.version_info[0] == 3, "Requires Python 3")
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

def activate_via_with_statement(handler):
    return handler

@contextmanager
def activate_via_push_pop(handler):
    handler.push_thread()
    try:
        yield handler
    finally:
        handler.pop_thread()

@contextmanager
def capturing_stderr_context():
    original = sys.stderr
    sys.stderr = StringIO()
    try:
        yield sys.stderr
    finally:
        sys.stderr = original
