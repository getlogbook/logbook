"""Tests logging file handler in comparison"""
from logging import FileHandler, getLogger
from tempfile import NamedTemporaryFile

log = getLogger("Testlogger")


def run():
    f = NamedTemporaryFile()
    handler = FileHandler(f.name)
    log.addHandler(handler)
    for x in range(500):
        log.warning("this is handled")
