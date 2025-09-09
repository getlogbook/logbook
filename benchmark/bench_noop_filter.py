from io import StringIO

from logbook import Logger, NullHandler, StreamHandler

log = Logger("Test logger")


def run():
    out = StringIO()
    with NullHandler():
        with StreamHandler(out, filter=lambda r, h: False):
            for _ in range(500):
                log.warning("this is not handled")
    assert not out.getvalue()
