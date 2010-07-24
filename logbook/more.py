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
    """A logger that attaches a tag to each record."""

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


class JinjaFormatter(object):
    """A formatter object that makes it easy to format using a Jinja 2
    template instead of a format string.
    """

    def __init__(self, template):
        try:
            from jinja2 import Environment
        except ImportError:
            raise RuntimeError('The jinja2 module could not be imported')
        self.environment = Environment()
        self.template = self.environment.from_string(template)

    def __call__(self, record, handler):
        return self.template.render(record=record, handler=handler)
