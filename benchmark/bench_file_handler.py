"""Benchmarks the file handler"""
from tempfile import NamedTemporaryFile

from logbook import FileHandler, Logger

log = Logger("Test logger")


def run():
    f = NamedTemporaryFile()
    with FileHandler(f.name) as handler:
        for x in range(500):
            log.warning("this is handled")
