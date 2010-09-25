"""Benchmarks the file handler with unicode"""
from logbook import Logger, FileHandler
from tempfile import NamedTemporaryFile


log = Logger('Test logger')


def run():
    f = NamedTemporaryFile()
    with FileHandler(f.name) as handler:
        for x in xrange(500):
            log.warning(u'this is handled \x6f')
