"""Tests with a logging handler becoming a noop for comparison"""
from io import StringIO
from logging import ERROR, StreamHandler, getLogger

log = getLogger("Testlogger")


def run():
    out = StringIO()
    handler = StreamHandler(out)
    handler.setLevel(ERROR)
    log.addHandler(handler)
    for x in range(500):
        log.warning("this is not handled")
