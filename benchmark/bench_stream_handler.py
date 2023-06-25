"""Tests the stream handler"""
from cStringIO import StringIO

from logbook import Logger, StreamHandler

log = Logger("Test logger")


def run():
    out = StringIO()
    with StreamHandler(out) as handler:
        for x in xrange(500):
            log.warning("this is not handled")
    assert out.getvalue().count("\n") == 500
