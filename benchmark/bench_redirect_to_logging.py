"""Tests redirects from logging to logbook"""
from logging import StreamHandler, getLogger

from cStringIO import StringIO

from logbook.compat import LoggingHandler

log = getLogger("Test logger")


def run():
    out = StringIO()
    log.addHandler(StreamHandler(out))
    with LoggingHandler():
        for x in xrange(500):
            log.warning("this is not handled")
    assert out.getvalue().count("\n") == 500
