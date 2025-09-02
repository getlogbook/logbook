"""Tests with frame introspection disabled"""

from logbook import Flags, Logger, NullHandler

log = Logger("Test logger")


class DummyHandler(NullHandler):
    blackhole = False


def run():
    with Flags(introspection=False):
        with DummyHandler():
            for _ in range(500):
                log.warning("this is not handled")
