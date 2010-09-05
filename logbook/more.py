# -*- coding: utf-8 -*-
"""
    logbook.more
    ~~~~~~~~~~~~

    Fancy stuff for logbook.

    :copyright: (c) 2010 by Armin Ronacher, Georg Brandl.
    :license: BSD, see LICENSE for more details.
"""

import re
import os
import sys
import time
from collections import deque
from threading import Lock, Thread
from multiprocessing import Queue
from Queue import Empty
from cgi import parse_qsl
from urllib import urlencode


from logbook.base import LogRecord, RecordDispatcher, NOTSET, ERROR, WARNING
from logbook.handlers import Handler, StringFormatter, StringFormatterHandlerMixin
from logbook.helpers import json, get_application_name


_ws_re = re.compile(r'(\s+)(?u)')
_traceback_file_re = re.compile(r'\s+File.*,line \d+, in')
TWITTER_FORMAT_STRING = \
u'[{record.channel}] {record.level_name}: {record.message}'
TWITTER_ACCESS_TOKEN_URL = 'https://twitter.com/oauth/access_token'
NEW_TWEET_URL = 'https://api.twitter.com/1/statuses/update.json'


class TaggingLogger(RecordDispatcher):
    """A logger that attaches a tag to each record.  This is an alternative
    record dispatcher that does not use levels but tags to keep log
    records apart.  It is constructed with a descriptive name and at least
    one tag.  The tags are up for you to define::

        logger = TaggingLogger('My Logger', ['info', 'warning'])

    For each tag defined that way, a method appears on the logger with
    that name::

        logger.info('This is a info message')

    To dispatch to different handlers based on tags you can use the
    :class:`TaggingHandler`.

    The tags themselves are stored as list named ``'tags'`` in the
    :attr:`~logbook.LogRecord.extra` dictionary.
    """

    def __init__(self, name=None, tags=None):
        RecordDispatcher.__init__(self, name)
        # create a method for each tag named
        list(setattr(self, tag, lambda msg, *args, **kwargs:
            self.log(tag, msg, *args, **kwargs)) for tag in (tags or ()))

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

        handler = TaggingHandler(dict(
            info=OneHandler(),
            warning=AnotherHandler()
        ))
    """

    def __init__(self, handlers, filter=None, bubble=False):
        Handler.__init__(self, NOTSET, filter, bubble)
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
            return FingersCrossedHandler(factory)

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

    def __init__(self, handler, action_level=ERROR, buffer_size=0,
                 pull_information=True, filter=None, bubble=False):
        Handler.__init__(self, NOTSET, filter, bubble)
        self.lock = Lock()
        self._level = action_level
        if isinstance(handler, Handler):
            self._handler = handler
            self._handler_factory = None
        else:
            self._handler = None
            self._handler_factory = handler
        #: the buffered records of the handler.  Once the action is triggered
        #: (:attr:`triggered`) this list will be None.  This attribute can
        #: be helpful for the handler factory function to select a proper
        #: filename (for example time of first log record)
        self.buffered_records = deque()
        #: the maximum number of entries in the buffer.  If this is exhausted
        #: the oldest entries will be discarded to make place for new ones
        self.buffer_size = buffer_size
        self._buffer_full = False
        self._pull_information = pull_information
        self._action_triggered = False

    def close(self):
        if self._handler is not None:
            self._handler.close()

    def enqueue(self, record):
        assert self.buffered_records is not None, 'rollover occurred'
        if self._pull_information:
            record.pull_information()
        self.buffered_records.append(record)
        if self._buffer_full:
            self.buffered_records.popleft()
        elif self.buffer_size and \
             len(self.buffered_records) >= self.buffer_size - 1:
            self._buffer_full = True

    def rollover(self, record):
        assert self.buffered_records is not None, 'rollover occurred'
        if self._handler is None:
            self._handler = self._handler_factory(record, self)
        for old_record in self.buffered_records:
            self._handler.emit(old_record)
        self.buffered_records = None
        self._action_triggered = True

    @property
    def triggered(self):
        """This attribute is `True` when the action was triggered.  From
        this point onwards the finger crossed handler transparently
        forwards all log records to the inner handler.
        """
        return self._action_triggered

    def emit(self, record):
        with self.lock:
            if self._action_triggered:
                self._handler.emit(record)
            elif record.level >= self._level:
                self.rollover(record)
                self._handler.emit(record)
            else:
                self.enqueue(record)


class MultiProcessingHandler(Handler):
    """Implements a handler that dispatches to another handler directly
    from the same processor or with the help of a unix pipe from the
    child processes to the parent.
    """

    # XXX: this should use a smilar interface to the ZeroMQ subscriber
    # which breaks up sender and receiver into two parts and provides an
    # interface to shut down the subscriber thread.  Additionally and
    # more importantly it does not deliver to a handler but dispatches
    # to a setup which is more useful

    def __init__(self, handler, level=NOTSET, filter=None, bubble=False):
        Handler.__init__(self, level, filter, bubble)
        self.handler = handler
        self.queue = Queue(-1)

        # start a thread in this process that receives data from the pipe
        self._alive = True
        self._rec_thread = Thread(target=self.receive)
        self._rec_thread.setDaemon(True)
        self._rec_thread.start()

        # necessary for older python's to disable a broken monkeypatch
        # in the logging module.  See multiprocessing/util.py for the
        # hasattr() check.  At least in Python 2.6.1 the multiprocessing
        # module is not imported by logging and as such the test in
        # the util fails.
        import logging, multiprocessing
        logging.multiprocessing = multiprocessing

    def close(self):
        if not self._alive:
            return
        self._alive = False
        self._rec_thread.join()
        self.queue.close()
        self.queue.join_thread()

    def receive(self):
        while self._alive:
            try:
                item = self.queue.get(timeout=0.25)
            except Empty:
                continue
            self.handler.handle(LogRecord.from_dict(item))

    def emit(self, record):
        self.queue.put_nowait(record.to_dict(json_safe=True))


class GrowlHandler(Handler):
    """A handler that dispatches to Growl.  Requires that either growl-py or
    py-Growl are installed.
    """

    def __init__(self, application_name=None, icon=None, host=None,
                 password=None, level=NOTSET, filter=None, bubble=False):
        Handler.__init__(self, level, filter, bubble)

        # growl is using the deprecated md5 module, but we really don't need
        # to see that deprecation warning
        from warnings import filterwarnings
        filterwarnings(module='Growl', category=DeprecationWarning,
                       action='ignore')

        try:
            import Growl
            self._growl = Growl
        except ImportError:
            raise RuntimeError('The growl module is not available.  You have '
                               'to install either growl-py or py-Growl to '
                               'use the GrowlHandler.')

        # if no application name is provided, guess it from the executable
        if application_name is None:
            application_name = get_application_name()

        if icon is not None:
            if not os.path.isfile(icon):
                raise IOError('Filename to an icon expected.')
            icon = self._growl.Image.imageFromPath(icon)
        else:
            try:
                icon = self._growl.Image.imageWithIconForCurrentApplication()
            except TypeError:
                icon = None

        self.application_name = application_name
        self._notifier = self._growl.GrowlNotifier(
            applicationName=application_name,
            applicationIcon=icon,
            notifications=['Notset', 'Debug', 'Info', 'Notice', 'Warning',
                           'Error', 'Critical'],
            hostname=host,
            password=password
        )
        self._notifier.register()

    def is_sticky(self, record):
        """Returns `True` if the sticky flag should be set for this record.
        The default implementation marks errors and criticals sticky.
        """
        return record.level >= ERROR

    def get_priority(self, record):
        """Returns the priority flag for Growl.  Errors and criticals are
        get highest priority (2), warnings get higher priority (1) and the
        rest gets 0.  Growl allows values between -2 and 2.
        """
        if record.level >= ERROR:
            return 2
        elif record.level == WARNING:
            return 1
        return 0

    def make_title(self, record):
        """Called to get the title from the record."""
        return u'%s: %s' % (record.channel, record.level_name.title())

    def make_text(self, record):
        """Called to get the text of the record."""
        return record.message

    def emit(self, record):
        title = self.make_title(record)
        text = self.make_text(record)
        self._notifier.notify(record.level_name.title(), title, text,
                              sticky=self.is_sticky(record),
                              priority=self.get_priority(record))


class PyNotifyHandler(Handler):
    """A handler that dispatches to libnotify.  Requires pynotify installed."""

    def __init__(self, application_name=None, icon=None, level=NOTSET,
                 filter=None, bubble=False):
        Handler.__init__(self, level, filter, bubble)

        try:
            import pynotify
            self._pynotify = pynotify
        except ImportError:
            raise RuntimeError('The pynotify library is required for '
                               'the PyNotifyHandler.')

        if application_name is None:
            application_name = get_application_name()
        pynotify.init(application_name)
        self.icon = icon

    def set_icon(self, notifier, icon):
        try:
            from gtk import gdk
        except ImportError:
            #TODO: raise a warning?
            raise RuntimeError('The gtk.gdk module is required to set an icon.')

        if icon is not None:
            if not isinstance(icon, gdk.Pixbuf):
                icon = gdk.pixbuf_new_from_file(icon)
            notifier.set_icon_from_pixbuf(icon)

    def get_expires(self, record):
        """Returns either EXPIRES_DEFAULT or EXPIRES_NEVER for this record.
        The default implementation marks errors and criticals as EXPIRES_NEVER.
        """
        pn = self._pynotify
        return pn.EXPIRES_NEVER if record.level >= ERROR else pn.EXPIRES_DEFAULT

    def get_urgency(self, record):
        """Returns the urgency flag for pynotify.  Errors and criticals are
        get highest urgency (CRITICAL), warnings get higher priority (NORMAL)
        and the rest gets LOW.
        """
        pn = self._pynotify
        if record.level >= ERROR:
            return pn.URGENCY_CIRITICAL
        elif record.level == WARNING:
            return pn.URGENCY_NORMAL
        return pn.URGENCY_LOW

    def make_summary(self, record):
        """Called to get the summary from the record."""
        return u'%s: %s' % (record.channel, record.level_name.title())

    def make_body(self, record):
        """Called to get the body of the record."""
        return record.message

    def emit(self, record):
        summary = self.make_summary(record)
        body = self.make_body(record)
        notifier = self._pynotify.Notification(summary, body)
        notifier.set_urgency(self.get_urgency(record))
        notifier.set_timeout(self.get_expires(record))
        self.set_icon(notifier, self.icon)
        notifier.show()


class TwitterFormatter(StringFormatter):
    """Works like the standard string formatter and is used by the
    :class:`TwitterHandler` unless changed.
    """
    max_length = 140

    def format_exception(self, record):
        # operate on the formatted exception instead of exc_info so
        # that this also works if we deal with closed records
        lines = (record.formatted_exception or '').splitlines()
        lines.reverse()
        for idx, line in enumerate(lines):
            if _traceback_file_re.match(line):
                return u' '.join(u' '.join(reversed(lines[:idx])).split())
        return u''

    def __call__(self, record, handler):
        formatted = StringFormatter.__call__(self, record, handler)
        rv = []
        length = 0
        for piece in _ws_re.split(formatted):
            length += len(piece)
            if length > self.max_length:
                if length - len(piece) < self.max_length:
                    rv.append(u'…')
                break
            rv.append(piece)
        return u''.join(rv)


class TwitterHandler(Handler, StringFormatterHandlerMixin):
    """A handler that logs to twitter.  Requires that you sign up an
    application on twitter and request xauth support.  Furthermore the
    oauth2 library has to be installed.
    """
    default_format_string = TWITTER_FORMAT_STRING
    formatter_class = TwitterFormatter

    def __init__(self, consumer_key, consumer_secret, username,
                 password, level=NOTSET, format_string=None, filter=None,
                 bubble=False):
        Handler.__init__(self, level, filter, bubble)
        StringFormatterHandlerMixin.__init__(self, format_string)
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret
        self.username = username
        self.password = password

        try:
            import oauth2
        except ImportError:
            raise RuntimeError('The python-oauth2 library is required for '
                               'the TwitterHandler.')

        self._oauth = oauth2
        self._oauth_token = None
        self._oauth_token_secret = None
        self._consumer = oauth2.Consumer(consumer_key,
                                         consumer_secret)
        self._client = oauth2.Client(self._consumer)

    def get_oauth_token(self):
        """Returns the oauth access token."""
        if self._oauth_token is None:
            resp, content = self._client.request(
                TWITTER_ACCESS_TOKEN_URL + '?', 'POST',
                body=urlencode({
                    'x_auth_username':  self.username.encode('utf-8'),
                    'x_auth_password':  self.password.encode('utf-8'),
                    'x_auth_mode':      'client_auth'
                }),
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            )
            if resp['status'] != '200':
                raise RuntimeError('unable to login to Twitter')
            data = dict(parse_qsl(content))
            self._oauth_token = data['oauth_token']
            self._oauth_token_secret = data['oauth_token_secret']
        return self._oauth.Token(self._oauth_token,
                                 self._oauth_token_secret)

    def make_client(self):
        """Creates a new oauth client auth a new access token."""
        return self._oauth.Client(self._consumer, self.get_oauth_token())

    def tweet(self, status):
        """Tweets a given status.  Status must not exceed 140 chars."""
        client = self.make_client()
        resp, content = client.request(NEW_TWEET_URL, 'POST',
            body=urlencode({'status': status.encode('utf-8')}),
            headers={'Content-Type': 'application/x-www-form-urlencoded'})
        return resp['status'] == '200'

    def emit(self, record):
        self.tweet(self.format(record))


class JinjaFormatter(object):
    """A formatter object that makes it easy to format using a Jinja 2
    template instead of a format string.
    """

    def __init__(self, template):
        try:
            from jinja2 import Template
        except ImportError:
            raise RuntimeError('The jinja2 library is required for '
                               'the JinjaFormatter.')
        self.template = Template(template)

    def __call__(self, record, handler):
        return self.template.render(record=record, handler=handler)
