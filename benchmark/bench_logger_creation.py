"""Test with no handler active"""

from logbook import Logger


def run():
    for _ in range(500):
        Logger("Test")
