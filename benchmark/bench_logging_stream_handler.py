"""Tests the stream handler in logging"""
from io import StringIO
from logging import Logger, StreamHandler

log = Logger("Test logger")


def run():
    out = StringIO()
    log.addHandler(StreamHandler(out))
    for x in range(500):
        log.warning("this is not handled")
    assert out.getvalue().count("\n") == 500
