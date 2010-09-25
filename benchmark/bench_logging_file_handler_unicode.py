"""Tests logging file handler in comparison"""
from logging import getLogger, FileHandler
from tempfile import NamedTemporaryFile


log = getLogger('Testlogger')


def run():
    f = NamedTemporaryFile()
    handler = FileHandler(f.name)
    log.addHandler(handler)
    for x in xrange(500):
        log.warning(u'this is handled \x6f')
