# -*- coding: utf-8 -*-
"""
    logbook.pycompat.python25
    ~~~~~~~~~~~~~~~~~~~~~~~~~

    :copyright: (c) by Daniel Neuhäuser.
    :license: BSD, see LICENSE for more details.
"""
import sys


if sys.version_info[:2] < (2, 5):
    raise ImportError()


from contextlib import contextmanager


class StackedObjectBase(object):
    @contextmanager
    def threadbound(self):
        """Can be used in combination with the `with` statement to
        execute code while the object is bound to the thread.
        """
        self.push_thread()
        try:
            yield self
        finally:
            self.pop_thread()

    @contextmanager
    def applicationbound(self):
        """Can be used in combination with the `with` statement to
        execute code while the object is bound to the application.
        """
        self.push_application()
        try:
            yield self
        finally:
            self.pop_application()
