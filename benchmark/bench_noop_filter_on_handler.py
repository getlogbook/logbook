"""Like the filter test, but with the should_handle implemented"""
from io import StringIO

from logbook import Logger, NullHandler, StreamHandler

log = Logger("Test logger")


class CustomStreamHandler(StreamHandler):
    def should_handle(self, record):
        return False


def run():
    out = StringIO()
    with NullHandler():
        with CustomStreamHandler(out) as handler:
            for x in range(500):
                log.warning("this is not handled")
    assert not out.getvalue()
