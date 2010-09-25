"""Test with no handler active"""
from logging import getLogger


root_logger = getLogger()


def run():
    for x in xrange(500):
        getLogger('Test')
        del root_logger.manager.loggerDict['Test']
