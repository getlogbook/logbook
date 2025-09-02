"""Tests the test handler"""

from logbook import Logger, TestHandler

log = Logger("Test logger")


def run():
    with TestHandler() as handler:
        for _ in range(500):
            log.warning("this is not handled")
