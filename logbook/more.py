# -*- coding: utf-8 -*-
"""
    logbook.more
    ~~~~~~~~~~~~

    Fancy stuff for logbook.

    :copyright: (c) 2010 by Armin Ronacher, Georg Brandl.
    :license: BSD, see LICENSE for more details.
"""

from logbook.base import Logger, NOTSET, WARNING
from logbook.handlers import Handler


class FingersCrossedHandler(Handler):
    def __init__(self, handler, action_level=WARNING):
        Handler.__init__(self)
        self._level = action_level
        self._handler = handler
        self._records = []
        self._seen_error = False

    def contextbound(self, processor=None, bubble=True):
        del self._records[:]
        self._seen_error = False
        return Handler.contextbound(self, processor, bubble)

    def emit(self, record):
        if self._seen_error:
            return self._handler.emit(record)
        elif record.level >= self._level:
            for old_record in self._records:
                self._handler.emit(old_record)
            self._handler.emit(record)
            self._seen_error = True
        else:
            self._records.append(record)
