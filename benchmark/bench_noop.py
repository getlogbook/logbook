"""Test with no handler active"""
from cStringIO import StringIO

from logbook import ERROR, Logger, NullHandler, StreamHandler

log = Logger("Test logger")


def run():
    out = StringIO()
    with NullHandler():
        with StreamHandler(out, level=ERROR) as handler:
            for x in xrange(500):
                log.warning("this is not handled")
    assert not out.getvalue()
