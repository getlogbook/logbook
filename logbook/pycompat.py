# -*- coding: utf-8 -*-
"""
    logbook.pycompat
    ~~~~~~~~~~~~~~~~

    :copyright: (c) by Daniel Neuhäuser.
    :license: BSD, see LICENSE for more details.
"""
try:
    any
    all
except NameError:
    def any(iterable):
        for item in iterable:
            if item:
                return True

    def all(iterable):
        for item in iterable:
            if not item:
                return True
else:
    any = any
    all = all


try:
    str.partition
    unicode.partition
except AttributeError:
    def partition(string, sep):
        try:
            index = string.index(sep)
        except ValueError:
            return string, '', ''
        return string[:index], sep, string[index + len(sep):]
else:
    def partition(string, sep):
        return string.__class__.partition(string, sep)
