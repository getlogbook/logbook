# -*- coding: utf-8 -*-
"""
    logbook.more
    ~~~~~~~~~~~~

    Fancy stuff for logbook.

    :copyright: (c) 2010 by Armin Ronacher, Georg Brandl.
    :license: BSD, see LICENSE for more details.
"""

import sys

from logbook.base import LogRecord, RecordDispatcher, NOTSET, WARNING
from logbook.handlers import Handler


class TaggingLogger(RecordDispatcher):

    def __init__(self, name=None, *tags):
        RecordDispatcher.__init__(self, name)
        # create a method for each tag named
        list(setattr(self, tag, lambda msg, *args, **kwargs:
                     self.log(tag, msg, *args, **kwargs)) for tag in tags)

    def process_record(self, record):
        pass

    def log(self, tags, msg, *args, **kwargs):
        if isinstance(tags, basestring):
            tags = [tags]
        exc_info = kwargs.pop('exc_info', None)
        extra = kwargs.pop('extra', {})
        extra['tags'] = list(tags)
        record = LogRecord(self.name, NOTSET, msg, args, kwargs, exc_info,
                           extra, sys._getframe(1))
        self.process_record(record)
        try:
            self.handle(record)
        finally:
            record.close()


class TaggingHandler(Handler):

    def __init__(self, **handlers):
        Handler.__init__(self)
        assert isinstance(handlers, dict)
        self._handlers = dict(
            (tag, isinstance(handler, Handler) and [handler] or handler)
            for (tag, handler) in handlers.iteritems())

    def emit(self, record):
        for tag in record.extra['tags']:
            for handler in self._handlers.get(tag, []):
                handler.emit(record)


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

    def applicationbound(self, processor=None, bubble=True):
        del self._records[:]
        self._seen_error = False
        return Handler.applicationbound(self, processor, bubble)

    def emit(self, record):
        if self._seen_error:
            return self._handler.emit(record)
        elif record.level >= self._level:
            for old_record in self._records:
                self._handler.emit(old_record)
            self._handler.emit(record)
            self._seen_error = True
        else:
            #record.pull_information()
            self._records.append(record)
