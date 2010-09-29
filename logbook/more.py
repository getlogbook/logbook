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
from cgi import parse_qsl
from urllib import urlencode

from logbook.base import RecordDispatcher, NOTSET, ERROR, NOTICE
from logbook.handlers import Handler, StringFormatter, \
     StringFormatterHandlerMixin, StderrHandler
from logbook._termcolors import colorize
from logbook.helpers import F


_ws_re = re.compile(r'(\s+)(?u)')
TWITTER_FORMAT_STRING = \
u'[{record.channel}] {record.level_name}: {record.message}'
TWITTER_ACCESS_TOKEN_URL = 'https://twitter.com/oauth/access_token'
NEW_TWEET_URL = 'https://api.twitter.com/1/statuses/update.json'


class TwitterFormatter(StringFormatter):
    """Works like the standard string formatter and is used by the
    :class:`TwitterHandler` unless changed.
    """
    max_length = 140

    def format_exception(self, record):
        return u'%s: %s' % (record.exception_shortname,
                            record.exception_message)

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
        return self.make_record_and_handle(NOTSET, msg, args, kwargs,
                                           exc_info, extra)


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


class TwitterHandler(Handler, StringFormatterHandlerMixin):
    """A handler that logs to twitter.  Requires that you sign up an
    application on twitter and request xauth support.  Furthermore the
    oauth2 library has to be installed.

    If you don't want to register your own application and request xauth
    credentials, there are a couple of leaked consumer key and secret
    pairs from application explicitly whitelisted at Twitter
    (`leaked secrets <http://bit.ly/leaked-secrets>`_).
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


class ExternalApplicationHandler(Handler):
    """This handler invokes an external application to send parts of
    the log record to.  The constructor takes a list of arguments that
    are passed to another application where each of the arguments is a
    format string, and optionally a format string for data that is
    passed to stdin.

    For example it can be used to invoke the ``say`` command on OS X::

        from logbook.more import ExternalApplicationHandler
        say_handler = ExternalApplicationHandler(['say', '{record.message}'])

    Note that the above example is blocking until ``say`` finished, so it's
    recommended to combine this handler with the
    :class:`logbook.ThreadedWrapperHandler` to move the execution into
    a background thread.

    .. versionadded:: 0.3
    """

    def __init__(self, arguments, stdin_format=None,
                 encoding='utf-8', level=NOTSET, filter=None,
                 bubble=False):
        Handler.__init__(self, level, filter, bubble)
        self.encoding = encoding
        self._arguments = [F(arg) for arg in arguments]
        if stdin_format is not None:
            stdin_format = F(stdin_format)
        self._stdin_format = stdin_format
        import subprocess
        self._subprocess = subprocess

    def emit(self, record):
        args = [arg.format(record=record).encode(self.encoding)
                for arg in self._arguments]
        if self._stdin_format is not None:
            stdin_data = self._stdin_format.format(record=record) \
                                           .encode(self.encoding)
            stdin = self._subprocess.PIPE
        else:
            stdin = None
        c = self._subprocess.Popen(args, stdin=stdin)
        if stdin is not None:
            c.communicate(stdin_data)
        c.wait()


class ColorizingStreamHandlerMixin(object):
    """A mixin class that does colorizing.

    .. versionadded:: 0.3
    """

    def should_colorize(self, record):
        """Returns `True` if colorizing should be applied to this
        record.  The default implementation returns `True` if the
        stream is a tty and we are not executing on windows.
        """
        if os.name == 'nt':
            return False
        isatty = getattr(self.stream, 'isatty', None)
        return isatty and isatty()

    def get_color(self, record):
        """Returns the color for this record."""
        if record.level >= ERROR:
            return 'red'
        elif record.level >= NOTICE:
            return 'yellow'
        return 'lightgray'

    def format_and_encode(self, record):
        rv = super(ColorizingStreamHandlerMixin, self) \
                .format_and_encode(record)
        if self.should_colorize(record):
            color = self.get_color(record)
            if color:
                rv = colorize(color, rv)
        return rv


class ColorizedStderrHandler(ColorizingStreamHandlerMixin, StderrHandler):
    """A colorizing stream handler that writes to stderr.  It will only
    colorize if a terminal was detected.  Note that this handler does
    not colorize on Windows systems.

    .. versionadded:: 0.3
    """


# backwards compat.  Should go away in some future releases
from logbook.handlers import FingersCrossedHandler as \
     FingersCrossedHandlerBase
class FingersCrossedHandler(FingersCrossedHandlerBase):
    def __init__(self, *args, **kwargs):
        FingersCrossedHandlerBase.__init__(self, *args, **kwargs)
        from warnings import warn
        warn(PendingDeprecationWarning('fingers crossed handler changed '
            'location.  It\'s now a core component of Logbook.'))


class ExceptionHandler(Handler, StringFormatterHandlerMixin):
    """An exception handler which raises exceptions of the given `exc_type`.
    This is especially useful if you set a specific error `level` e.g. to treat
    warnings as exceptions::

        from logbook.more import ExceptionHandler

        class ApplicationWarning(Exception):
            pass

        exc_handler = ExceptionHandler(ApplicationWarning, level='WARNING')

    .. versionadded:: 0.3
    """
    def __init__(self, exc_type, level=NOTSET, format_string=None,
                 filter=None, bubble=False):
        Handler.__init__(self, level, filter, bubble)
        StringFormatterHandlerMixin.__init__(self, format_string)
        self.exc_type = exc_type

    def handle(self, record):
        if self.should_handle(record):
            raise self.exc_type(self.format(record))
        return False
