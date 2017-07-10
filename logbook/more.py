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
import platform

from collections import defaultdict
from functools import partial

from logbook.base import (
    RecordDispatcher, dispatch_record, NOTSET, ERROR, NOTICE)
from logbook.handlers import (
    Handler, StringFormatter, StringFormatterHandlerMixin, StderrHandler)
from logbook._termcolors import colorize
from logbook.helpers import PY2, string_types, iteritems, u
from logbook.ticketing import TicketingHandler as DatabaseHandler
from logbook.ticketing import BackendBase

try:
    import riemann_client.client
    import riemann_client.transport
except ImportError:
    riemann_client = None
    #from riemann_client.transport import TCPTransport, UDPTransport, BlankTransport


if PY2:
    from urllib import urlencode
    from urlparse import parse_qsl
else:
    from urllib.parse import parse_qsl, urlencode

_ws_re = re.compile(r'(\s+)(?u)')
TWITTER_FORMAT_STRING = u(
    '[{record.channel}] {record.level_name}: {record.message}')
TWITTER_ACCESS_TOKEN_URL = 'https://twitter.com/oauth/access_token'
NEW_TWEET_URL = 'https://api.twitter.com/1/statuses/update.json'


class CouchDBBackend(BackendBase):
    """Implements a backend that writes into a CouchDB database.
    """
    def setup_backend(self):
        from couchdb import Server

        uri = self.options.pop('uri', u(''))
        couch = Server(uri)
        db_name = self.options.pop('db')
        self.database = couch[db_name]

    def record_ticket(self, record, data, hash, app_id):
        """Records a log record as ticket.
        """
        db = self.database

        ticket = record.to_dict()
        ticket["time"] = ticket["time"].isoformat() + "Z"
        ticket_id, _ = db.save(ticket)

        db.save(ticket)


class TwitterFormatter(StringFormatter):
    """Works like the standard string formatter and is used by the
    :class:`TwitterHandler` unless changed.
    """
    max_length = 140

    def format_exception(self, record):
        return u('%s: %s') % (record.exception_shortname,
                              record.exception_message)

    def __call__(self, record, handler):
        formatted = StringFormatter.__call__(self, record, handler)
        rv = []
        length = 0
        for piece in _ws_re.split(formatted):
            length += len(piece)
            if length > self.max_length:
                if length - len(piece) < self.max_length:
                    rv.append(u('…'))
                break
            rv.append(piece)
        return u('').join(rv)


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
        for tag in (tags or ()):
            setattr(self, tag, partial(self.log, tag))

    def log(self, tags, msg, *args, **kwargs):
        if isinstance(tags, string_types):
            tags = [tags]
        exc_info = kwargs.pop('exc_info', None)
        extra = kwargs.pop('extra', {})
        extra['tags'] = list(tags)
        frame_correction = kwargs.pop('frame_correction', 0)
        return self.make_record_and_handle(NOTSET, msg, args, kwargs,
                                           exc_info, extra, frame_correction)


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
            for (tag, handler) in iteritems(handlers))

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
        resp, content = client.request(
            NEW_TWEET_URL, 'POST',
            body=urlencode({'status': status.encode('utf-8')}),
            headers={'Content-Type': 'application/x-www-form-urlencoded'})
        return resp['status'] == '200'

    def emit(self, record):
        self.tweet(self.format(record))


class SlackHandler(Handler, StringFormatterHandlerMixin):

    """A handler that logs to slack.  Requires that you sign up an
    application on slack and request an api token.  Furthermore the
    slacker library has to be installed.
    """

    def __init__(self, api_token, channel, level=NOTSET, format_string=None, filter=None,
                 bubble=False):

        Handler.__init__(self, level, filter, bubble)
        StringFormatterHandlerMixin.__init__(self, format_string)
        self.api_token = api_token

        try:
            from slacker import Slacker
        except ImportError:
            raise RuntimeError('The slacker library is required for '
                               'the SlackHandler.')

        self.channel = channel
        self.slack = Slacker(api_token)

    def emit(self, record):
        self.slack.chat.post_message(channel=self.channel, text=self.format(record))


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
        self._arguments = list(arguments)
        if stdin_format is not None:
            stdin_format = stdin_format
        self._stdin_format = stdin_format
        import subprocess
        self._subprocess = subprocess

    def emit(self, record):
        args = [arg.format(record=record)
                for arg in self._arguments]
        if self._stdin_format is not None:
            stdin_data = (self._stdin_format.format(record=record)
                          .encode(self.encoding))
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
    .. versionchanged:: 1.0.0
       Added Windows support if `colorama`_ is installed.

    .. _`colorama`: https://pypi.python.org/pypi/colorama
    """
    _use_color = None

    def force_color(self):
        """Force colorizing the stream (`should_colorize` will return True)
        """
        self._use_color = True

    def forbid_color(self):
        """Forbid colorizing the stream (`should_colorize` will return False)
        """
        self._use_color = False

    def should_colorize(self, record):
        """Returns `True` if colorizing should be applied to this
        record.  The default implementation returns `True` if the
        stream is a tty. If we are executing on Windows, colorama must be
        installed.
        """
        if os.name == 'nt':
            try:
                import colorama
            except ImportError:
                return False
        if self._use_color is not None:
            return self._use_color
        isatty = getattr(self.stream, 'isatty', None)
        return isatty and isatty()

    def get_color(self, record):
        """Returns the color for this record."""
        if record.level >= ERROR:
            return 'red'
        elif record.level >= NOTICE:
            return 'yellow'
        return 'lightgray'

    def format(self, record):
        rv = super(ColorizingStreamHandlerMixin, self).format(record)
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
    .. versionchanged:: 1.0
       Added Windows support if `colorama`_ is installed.

    .. _`colorama`: https://pypi.python.org/pypi/colorama
    """
    def __init__(self, *args, **kwargs):
        StderrHandler.__init__(self, *args, **kwargs)

        # Try import colorama so that we work on Windows. colorama.init is a
        # noop on other operating systems.
        try:
            import colorama
        except ImportError:
            pass
        else:
            colorama.init()


# backwards compat.  Should go away in some future releases
from logbook.handlers import (
    FingersCrossedHandler as FingersCrossedHandlerBase)


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


class DedupHandler(Handler):
    """A handler that deduplicates log messages.

    It emits each unique log record once, along with the number of times it was
    emitted.
    Example:::

        with logbook.more.DedupHandler():
            logbook.error('foo')
            logbook.error('bar')
            logbook.error('foo')

    The expected output:::

       message repeated 2 times: foo
       message repeated 1 times: bar
    """
    def __init__(self,
                 format_string='message repeated {count} times: {message}',
                 *args, **kwargs):
        Handler.__init__(self, bubble=False, *args, **kwargs)
        self._format_string = format_string
        self.clear()

    def clear(self):
        self._message_to_count = defaultdict(int)
        self._unique_ordered_records = []

    def pop_application(self):
        Handler.pop_application(self)
        self.flush()

    def pop_thread(self):
        Handler.pop_thread(self)
        self.flush()

    def pop_greenlet(self):
        Handler.pop_greenlet(self)
        self.flush()

    def handle(self, record):
        if record.message not in self._message_to_count:
            self._unique_ordered_records.append(record)
        self._message_to_count[record.message] += 1
        return True

    def flush(self):
        for record in self._unique_ordered_records:
            record.message = self._format_string.format(
                message=record.message,
                count=self._message_to_count[record.message])
            # record.dispatcher is the logger who created the message,
            # it's sometimes supressed (by logbook.info for example)
            if record.dispatcher is not None:
                dispatch = record.dispatcher.call_handlers
            else:
                dispatch = dispatch_record
            dispatch(record)
        self.clear()


class RiemannHandler(Handler):

    """
    A handler that sends logs as events to Riemann.
    """

    def __init__(self,
                 host,
                 port,
                 message_type="tcp",
                 ttl=60,
                 flush_threshold=10,
                 bubble=False,
                 filter=None,
                 level=NOTSET):
        """
        :param host: riemann host
        :param port: riemann port
        :param message_type: selects transport. Currently available 'tcp' and 'udp'
        :param ttl: defines time to live in riemann
        :param flush_threshold: count of events after which we send to riemann
        """
        if riemann_client is None:
            raise NotImplementedError("The Riemann handler requires the riemann_client package") # pragma: no cover
        Handler.__init__(self, level, filter, bubble)
        self.host = host
        self.port = port
        self.ttl = ttl
        self.queue = []
        self.flush_threshold = flush_threshold
        if message_type == "tcp":
            self.transport = riemann_client.transport.TCPTransport
        elif message_type == "udp":
            self.transport = riemann_client.transport.UDPTransport
        elif message_type == "test":
            self.transport = riemann_client.transport.BlankTransport
        else:
            msg = ("Currently supported message types for RiemannHandler are: {0}. \
                    {1} is not supported."
                   .format(",".join(["tcp", "udp", "test"]), message_type))
            raise RuntimeError(msg)

    def record_to_event(self, record):
        from time import time
        tags = ["log", record.level_name]
        msg = str(record.exc_info[1]) if record.exc_info else record.msg
        channel_name = str(record.channel) if record.channel else "unknown"
        if any([record.level_name == keywords
                for keywords in ["ERROR", "EXCEPTION"]]):
            state = "error"
        else:
            state = "ok"
        return {"metric_f": 1.0,
                "tags": tags,
                "description": msg,
                "time": int(time()),
                "ttl": self.ttl,
                "host": platform.node(),
                "service": "{0}.{1}".format(channel_name, os.getpid()),
                "state": state
                }

    def _flush_events(self):
        with riemann_client.client.QueuedClient(self.transport(self.host, self.port)) as cl:
            for event in self.queue:
                cl.event(**event)
            cl.flush()
        self.queue = []

    def emit(self, record):
        self.queue.append(self.record_to_event(record))

        if len(self.queue) == self.flush_threshold:
            self._flush_events()
