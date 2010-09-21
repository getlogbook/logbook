# -*- coding: utf-8 -*-
"""
    logbook.pycompat.python24
    ~~~~~~~~~~~~~~~~~~~~~~~~~

    :copyright: (c) by Daniel Neuhäuser.
    :license: BSD, see LICENSE for more details.
"""
import sys


if sys.version_info[:2] > (2, 4):
    raise ImportError()


def any(iterable):
    for item in iterable:
        if item:
            return True


def all(iterable):
    for item in iterable:
        if not item:
            return False


def partition(string, sep):
    try:
        index = string.index(sep)
    except ValueError:
        return string, '', ''
    return string[:index], sep, string[index + len(sep):]


StackedObjectBase = object
