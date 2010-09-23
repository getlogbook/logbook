"""Tests with a logging handler becoming a noop for comparison"""
from logging import getLogger, StreamHandler, ERROR
from cStringIO import StringIO


log = getLogger('Testlogger')


def run():
    out = StringIO()
    handler = StreamHandler(out)
    handler.setLevel(ERROR)
    log.addHandler(handler)
    for x in xrange(500):
        log.warning('this is not handled')
