# -*- coding: utf-8 -*-
"""
    logbook.more
    ~~~~~~~~~~~~

    Fancy stuff for logbook.

    :copyright: (c) 2010 by Armin Ronacher, Georg Brandl.
    :license: BSD, see LICENSE for more details.
"""

import sys

from logbook.base import LogRecord, RecordDispatcher, NOTSET, ERROR
from logbook.handlers import Handler


class TaggingLogger(RecordDispatcher):
    """A logger that attaches a tag to each record.  This is an alternative
    record dispatcher that does not use levels but tags to keep log
    records apart.  It is constructed with a descriptive name and at least
    one tag.  The tags are up for you to define::

        logger = TaggingLogger('My Logger', 'info', 'warning')

    For each tag defined that way, a method appears on the logger with
    that name::

        logger.info('This is a info message')

    To dispatch to different handlers based on tags you can use the
    :class:`TaggingHandler`.

    The tags themselves are stored as list named ``'tags'`` in the
    :attr:`~logbook.LogRecord.extra` dictionary.
    """

    def __init__(self, name=None, *tags):
        RecordDispatcher.__init__(self, name)
        # create a method for each tag named
        list(setattr(self, tag, lambda msg, *args, **kwargs:
                     self.log(tag, msg, *args, **kwargs)) for tag in tags)

    def log(self, tags, msg, *args, **kwargs):
        if isinstance(tags, basestring):
            tags = [tags]
        exc_info = kwargs.pop('exc_info', None)
        extra = kwargs.pop('extra', {})
        extra['tags'] = list(tags)
        record = LogRecord(self.name, NOTSET, msg, args, kwargs, exc_info,
                           extra, sys._getframe(), self)
        try:
            self.handle(record)
        finally:
            record.close()


class TaggingHandler(Handler):
    """A handler that logs for tags and dispatches based on those.

    Example::

        import logbook
        from logbook.more import TaggingHandler

        handler = TaggingHandler(
            info=OneHandler(),
            warning=AnotherHandler()
        )
    """

    def __init__(self, **handlers):
        Handler.__init__(self)
        assert isinstance(handlers, dict)
        self._handlers = dict(
            (tag, isinstance(handler, Handler) and [handler] or handler)
            for (tag, handler) in handlers.iteritems())

    def emit(self, record):
        for tag in record.extra.get('tags', ()):
            for handler in self._handlers.get(tag, ()):
                handler.handle(record)


class FingersCrossedHandler(Handler):
    """This handler wraps another handler and will log everything in
    memory until a certain level (`action_level`, defaults to `ERROR`)
    is exceeded.  When that happens the fingers crossed handler will
    activate forever and log all buffered records as well as records
    yet to come into another handled which was passed to the constructor.

    Alternatively it's also possible to pass a factory function to the
    constructor instead of a handler.  That factory is then called with
    the triggering log entry and the finger crossed handler to create
    a handler which is then cached.

    The idea of this handler is to enable debugging of live systems.  For
    example it might happen that code works perfectly fine 99% of the time,
    but then some exception happens.  But the error that caused the
    exception alone might not be the interesting bit, the interesting
    information were the warnings that lead to the error.

    Here a setup that enables this for a web application::

        from logbook import FileHandler
        from logbook.more import FingersCrossedHandler

        def issue_logging():
            def factory(record, handler):
                return FileHandler('/var/log/app/issue-%s.log' % record.time)
            return FingersCrossedHandler(factory).threadbound(bubble=False)

        def application(environ, start_response):
            with issue_logging():
                return the_actual_wsgi_application(environ, start_response)

    Whenever an error occours, a new file in ``/var/log/app`` is created
    with all the logging calls that lead up to the error up to the point
    where the `with` block is exited.

    Please keep in mind that the :class:`~logbook.more.FingersCrossedHandler`
    handler is a one-time handler.  Once triggered, it will not reset.  Because
    of that you will have to re-create it whenever you bind it.  In this case
    the handler is created when it's bound to the thread.
    """

    def __init__(self, handler, action_level=ERROR,
                 pull_information=True):
        Handler.__init__(self)
        self._level = action_level
        if isinstance(handler, Handler):
            self._handler = handler
            self._handler_factory = None
        else:
            self._handler = None
            self._handler_factory = handler
        #: the buffered records of the handler.  Once the action is triggered
        #: (:attr:`triggered`) this list will be empty.  This attribute can
        #: be helpful for the handler factory function to select a proper
        #: filename (for example time of first log record)
        self.buffered_records = []
        self._pull_information = pull_information
        self._action_triggered = False

    def close(self):
        if self._handler is not None:
            self._handler.close()

    def enqueue(self, record):
        if self._pull_information:
            record.pull_information()
        self.buffered_records.append(record)

    @property
    def triggered(self):
        """This attribute is `True` when the action was triggered.  From
        this point onwards the finger crossed handler transparently
        forwards all log records to the inner handler.
        """
        return self._action_triggered

    def emit(self, record):
        if self._action_triggered:
            return self._handler.emit(record)
        elif record.level >= self._level:
            if self._handler is None:
                self._handler = self._handler_factory(record, self)
            for old_record in self.buffered_records:
                self._handler.emit(old_record)
            del self.buffered_records[:]
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
            from jinja2 import Template
        except ImportError:
            raise RuntimeError('JinjaFormatter requires the "jinja2" module '
                               'which could not be imported.')
        self.template = Template(template)

    def __call__(self, record, handler):
        return self.template.render(record=record, handler=handler)
