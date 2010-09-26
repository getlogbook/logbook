"""Benchmarks too low logger levels"""
from logbook import Logger, StreamHandler, ERROR
from cStringIO import StringIO


log = Logger('Test logger')
log.level = ERROR


def run():
    out = StringIO()
    with StreamHandler(out):
        for x in xrange(500):
            log.warning('this is not handled')
