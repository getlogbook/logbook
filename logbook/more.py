# -*- coding: utf-8 -*-
"""
    logbook.more
    ~~~~~~~~~~~~

    Fancy stuff for logbook.

    :copyright: (c) 2010 by Armin Ronacher, Georg Brandl.
    :license: BSD, see LICENSE for more details.
"""

import sys

from logbook.base import LogRecord, Logger, NOTSET, WARNING
from logbook.handlers import Handler


class TaggingLogger(Logger):
    """A logger that attaches a tag to each record."""

    def __init__(self, name=None, *tags):
        Logger.__init__(self, name)
        # create a method for each tag named
        list(setattr(self, tag, lambda msg, *args, **kwargs:
                     self.log(tag, msg, *args, **kwargs)) for tag in tags)

    def log(self, tags, *args, **kwargs):
        if isinstance(tags, basestring):
            tags = [tags]
        kwargs['extra'] = kwargs.get('extra', {})
        kwargs['extra']['tags'] = list(tags)
        Logger._log(self, NOTSET, args, kwargs)


class TaggingHandler(Handler):
    """A handler that logs for tags and dispatches based on those"""

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
    """This handler wraps another handler and will log everything in
    memory until a certain level is exceeded.
    """

    def __init__(self, handler, action_level=WARNING,
                 pull_information=True):
        Handler.__init__(self)
        self._level = action_level
        self._handler = handler
        self._records = []
        self._pull_information = pull_information
        self._action_triggered = False

    def enqueue(self, record):
        if self._pull_information:
            record.pull_information()
        self._records.append(record)

    def emit(self, record):
        if self._action_triggered:
            return self._handler.emit(record)
        elif record.level >= self._level:
            for old_record in self._records:
                self._handler.emit(old_record)
            del self._records[:]
            self._handler.emit(record)
            self._action_triggered = True
        else:
            self.enqueue(record)
