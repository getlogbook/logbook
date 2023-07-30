"""Test with no handler active"""
from io import StringIO

from logbook import ERROR, Logger, NullHandler, StreamHandler

log = Logger("Test logger")


def run():
    out = StringIO()
    with NullHandler():
        with StreamHandler(out, level=ERROR) as handler:
            for x in range(500):
                log.warning("this is not handled")
    assert not out.getvalue()
