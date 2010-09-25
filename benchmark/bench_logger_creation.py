"""Test with no handler active"""
from logbook import Logger


def run():
    for x in xrange(500):
        Logger('Test')
