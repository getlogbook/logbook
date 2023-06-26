"""Tests with a filter disabling a handler for comparsion in logging"""
from logging import Filter, StreamHandler, getLogger

from cStringIO import StringIO

log = getLogger("Testlogger")


class DisableFilter(Filter):
    def filter(self, record):
        return False


def run():
    out = StringIO()
    handler = StreamHandler(out)
    handler.addFilter(DisableFilter())
    log.addHandler(handler)
    for x in range(500):
        log.warning("this is not handled")
