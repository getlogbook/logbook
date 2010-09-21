# -*- coding: utf-8 -*-
"""
    logbook.pycompat
    ~~~~~~~~~~~~~~~~

    :copyright: (c) by Daniel Neuhäuser.
    :license: BSD, see LICENSE for more details.
"""
import sys

try:
    from logbook.pycompat.python25 import *
except (ImportError, SyntaxError):
    pass
try:
    from logbook.pycompat.python24 import *
except ImportError:
    pass


any = any
all = all
