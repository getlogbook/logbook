"""Tests with a logging handler becoming a noop for comparison"""
from io import StringIO
from logging import ERROR, StreamHandler, getLogger

log = getLogger("Testlogger")
log.setLevel(ERROR)


def run():
    out = StringIO()
    handler = StreamHandler(out)
    log.addHandler(handler)
    for x in range(500):
        log.warning("this is not handled")
