from logbook import Logger, StreamHandler, NullHandler
from cStringIO import StringIO


log = Logger('Test logger')


def run():
    out = StringIO()
    with NullHandler():
        with StreamHandler(out, filter=lambda r, h: False) as handler:
            for x in xrange(500):
                log.warning('this is not handled')
    assert not out.getvalue()
