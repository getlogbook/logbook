"""Benchmarks too low logger levels"""
from cStringIO import StringIO

from logbook import ERROR, Logger, StreamHandler

log = Logger('Test logger')
log.level = ERROR


def run():
    out = StringIO()
    with StreamHandler(out):
        for x in xrange(500):
            log.warning('this is not handled')
