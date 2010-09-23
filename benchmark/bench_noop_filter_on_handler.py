"""Like the filter test, but with the should_handle implemented"""
from logbook import Logger, StreamHandler, NullHandler
from cStringIO import StringIO


log = Logger('Test logger')


class CustomStreamHandler(StreamHandler):
    def should_handle(self, record):
        return False


def run():
    out = StringIO()
    with NullHandler():
        with CustomStreamHandler(out) as handler:
            for x in xrange(500):
                log.warning('this is not handled')
    assert not out.getvalue()
