"""Tests the stream handler"""
from logbook import Logger, StreamHandler
from cStringIO import StringIO


log = Logger('Test logger')


def run():
    out = StringIO()
    with StreamHandler(out) as handler:
        for x in xrange(500):
            log.warning('this is not handled')
    assert out.getvalue().count('\n') == 500
