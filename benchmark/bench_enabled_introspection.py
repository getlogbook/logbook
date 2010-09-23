"""Tests with stack frame introspection enabled"""
from logbook import Logger, NullHandler, Flags


log = Logger('Test logger')


class DummyHandler(NullHandler):
    blackhole = False


def run():
    with Flags(introspection=True):
        with DummyHandler() as handler:
            for x in xrange(500):
                log.warning('this is not handled')
