"""Test with no handler active"""
from logbook import Logger


def run():
    for x in range(500):
        Logger("Test")
