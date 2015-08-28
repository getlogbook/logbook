# -*- coding: utf-8 -*-
"""
    logbook.handlers
    ~~~~~~~~~~~~~~~~

    The handler interface and builtin handlers.

    :copyright: (c) 2010 by Armin Ronacher, Georg Brandl.
    :license: BSD, see LICENSE for more details.
"""
import os
import re
import sys
import stat
import errno
import socket
try:
    from hashlib import sha1
except ImportError:
    from sha import new as sha1
import traceback
from datetime import datetime, timedelta
from collections import deque

from logbook.base import CRITICAL, ERROR, WARNING, NOTICE, INFO, DEBUG, \
     NOTSET, level_name_property, _missing, lookup_level, \
     Flags, ContextObject, ContextStackManager
from logbook.helpers import rename, b, _is_text_stream, is_unicode, PY2, \
    zip, xrange, string_types, integer_types, reraise, u, with_metaclass
from logbook.concurrency import new_fine_grained_lock

DEFAULT_FORMAT_STRING = (
    u('[{record.time:%Y-%m-%d %H:%M:%S.%f}] ') +
    u('{record.level_name}: {record.channel}: {record.message}')
)
SYSLOG_FORMAT_STRING = u('{record.channel}: {record.message}')
NTLOG_FORMAT_STRING = u('''\
Message Level: {record.level_name}
Location: {record.filename}:{record.lineno}
Module: {record.module}
Function: {record.func_name}
Exact Time: {record.time:%Y-%m-%d %H:%M:%S}

Event provided Message:

{record.message}
''')
TEST_FORMAT_STRING = \
u('[{record.level_name}] {record.channel}: {record.message}')
MAIL_FORMAT_STRING = u('''\
Subject: {handler.subject}

Message type:       {record.level_name}
Location:           {record.filename}:{record.lineno}
Module:             {record.module}
Function:           {record.func_name}
Time:               {record.time:%Y-%m-%d %H:%M:%S}

Message:

{record.message}
''')
MAIL_RELATED_FORMAT_STRING = u('''\
Message type:       {record.level_name}
Location:           {record.filename}:{record.lineno}
Module:             {record.module}
Function:           {record.func_name}
{record.message}
''')

SYSLOG_PORT = 514

REGTYPE = type(re.compile("I'm a regular expression!"))

def create_syshandler(application_name, level=NOTSET):
    """Creates the handler the operating system provides.  On Unix systems
    this creates a :class:`SyslogHandler`, on Windows sytems it will
    create a :class:`NTEventLogHandler`.
    """
    if os.name == 'nt':
        return NTEventLogHandler(application_name, level=level)
    return SyslogHandler(application_name, level=level)


class _HandlerType(type):
    """The metaclass of handlers injects a destructor if the class has an
    overridden close method.  This makes it possible that the default
    handler class as well as all subclasses that don't need cleanup to be
    collected with less overhead.
    """

    def __new__(cls, name, bases, d):
        # aha, that thing has a custom close method.  We will need a magic
        # __del__ for it to be called on cleanup.
        if bases != (ContextObject,) and 'close' in d and '__del__' not in d \
           and not any(hasattr(x, '__del__') for x in bases):
            def _magic_del(self):
                try:
                    self.close()
                except Exception:
                    # del is also invoked when init fails, so we better just
                    # ignore any exception that might be raised here
                    pass
            d['__del__'] = _magic_del
        return type.__new__(cls, name, bases, d)


class Handler(with_metaclass(_HandlerType), ContextObject):
    """Handler instances dispatch logging events to specific destinations.

    The base handler class. Acts as a placeholder which defines the Handler
    interface. Handlers can optionally use Formatter instances to format
    records as desired. By default, no formatter is specified; in this case,
    the 'raw' message as determined by record.message is logged.

    To bind a handler you can use the :meth:`push_application`,
    :meth:`push_thread` or :meth:`push_greenlet` methods.  This will push the handler on a stack of
    handlers.  To undo this, use the :meth:`pop_application`,
    :meth:`pop_thread` methods and :meth:`pop_greenlet`::

        handler = MyHandler()
        handler.push_application()
        # all here goes to that handler
        handler.pop_application()

    By default messages sent to that handler will not go to a handler on
    an outer level on the stack, if handled.  This can be changed by
    setting bubbling to `True`.

    There are also context managers to setup the handler for the duration
    of a `with`-block::

        with handler.applicationbound():
            ...

        with handler.threadbound():
            ...

        with handler.greenletbound():
            ...

    Because `threadbound` is a common operation, it is aliased to a with
    on the handler itself if not using gevent::

        with handler:
            ...

    If gevent is enabled, the handler is aliased to `greenletbound`.
    """
    stack_manager = ContextStackManager()

    #: a flag for this handler that can be set to `True` for handlers that
    #: are consuming log records but are not actually displaying it.  This
    #: flag is set for the :class:`NullHandler` for instance.
    blackhole = False

    def __init__(self, level=NOTSET, filter=None, bubble=False):
        #: the level for the handler.  Defaults to `NOTSET` which
        #: consumes all entries.
        self.level = lookup_level(level)
        #: the formatter to be used on records.  This is a function
        #: that is passed a log record as first argument and the
        #: handler as second and returns something formatted
        #: (usually a unicode string)
        self.formatter = None
        #: the filter to be used with this handler
        self.filter = filter
        #: the bubble flag of this handler
        self.bubble = bubble

    level_name = level_name_property()

    def format(self, record):
        """Formats a record with the given formatter.  If no formatter
        is set, the record message is returned.  Generally speaking the
        return value is most likely a unicode string, but nothing in
        the handler interface requires a formatter to return a unicode
        string.

        The combination of a handler and formatter might have the
        formatter return an XML element tree for example.
        """
        if self.formatter is None:
            return record.message
        return self.formatter(record, self)

    def should_handle(self, record):
        """Returns `True` if this handler wants to handle the record.  The
        default implementation checks the level.
        """
        return record.level >= self.level

    def handle(self, record):
        """Emits the record and falls back.  It tries to :meth:`emit` the
        record and if that fails, it will call into :meth:`handle_error` with
        the record and traceback.  This function itself will always emit
        when called, even if the logger level is higher than the record's
        level.

        If this method returns `False` it signals to the calling function that
        no recording took place in which case it will automatically bubble.
        This should not be used to signal error situations.  The default
        implementation always returns `True`.
        """
        try:
            self.emit(record)
        except Exception:
            self.handle_error(record, sys.exc_info())
        return True

    def emit(self, record):
        """Emit the specified logging record.  This should take the
        record and deliver it to whereever the handler sends formatted
        log records.
        """

    def emit_batch(self, records, reason):
        """Some handlers may internally queue up records and want to forward
        them at once to another handler.  For example the
        :class:`~logbook.FingersCrossedHandler` internally buffers
        records until a level threshold is reached in which case the buffer
        is sent to this method and not :meth:`emit` for each record.

        The default behaviour is to call :meth:`emit` for each record in
        the buffer, but handlers can use this to optimize log handling.  For
        instance the mail handler will try to batch up items into one mail
        and not to emit mails for each record in the buffer.

        Note that unlike :meth:`emit` there is no wrapper method like
        :meth:`handle` that does error handling.  The reason is that this
        is intended to be used by other handlers which are already protected
        against internal breakage.

        `reason` is a string that specifies the rason why :meth:`emit_batch`
        was called, and not :meth:`emit`.  The following are valid values:

        ``'buffer'``
            Records were buffered for performance reasons or because the
            records were sent to another process and buffering was the only
            possible way.  For most handlers this should be equivalent to
            calling :meth:`emit` for each record.

        ``'escalation'``
            Escalation means that records were buffered in case the threshold
            was exceeded.  In this case, the last record in the iterable is the
            record that triggered the call.

        ``'group'``
            All the records in the iterable belong to the same logical
            component and happened in the same process.  For example there was
            a long running computation and the handler is invoked with a bunch
            of records that happened there.  This is similar to the escalation
            reason, just that the first one is the significant one, not the
            last.

        If a subclass overrides this and does not want to handle a specific
        reason it must call into the superclass because more reasons might
        appear in future releases.

        Example implementation::

            def emit_batch(self, records, reason):
                if reason not in ('escalation', 'group'):
                    Handler.emit_batch(self, records, reason)
                ...
        """
        for record in records:
            self.emit(record)

    def close(self):
        """Tidy up any resources used by the handler.  This is automatically
        called by the destructor of the class as well, but explicit calls are
        encouraged.  Make sure that multiple calls to close are possible.
        """

    def handle_error(self, record, exc_info):
        """Handle errors which occur during an emit() call.  The behaviour of
        this function depends on the current `errors` setting.

        Check :class:`Flags` for more information.
        """
        try:
            behaviour = Flags.get_flag('errors', 'print')
            if behaviour == 'raise':
                reraise(exc_info[0], exc_info[1], exc_info[2])
            elif behaviour == 'print':
                traceback.print_exception(*(exc_info + (None, sys.stderr)))
                sys.stderr.write('Logged from file %s, line %s\n' % (
                                 record.filename, record.lineno))
        except IOError:
            pass


class NullHandler(Handler):
    """A handler that does nothing.

    Useful to silence logs above a certain location in the handler stack::

        handler = NullHandler()
        handler.push_application()

    NullHandlers swallow all logs sent to them, and do not bubble them onwards.

    """
    blackhole = True

    def __init__(self, level=NOTSET, filter=None):
        super(NullHandler, self).__init__(level=level, filter=filter, bubble=False)


class WrapperHandler(Handler):
    """A class that can wrap another handler and redirect all calls to the
    wrapped handler::

        handler = WrapperHandler(other_handler)

    Subclasses should override the :attr:`_direct_attrs` attribute as
    necessary.
    """

    #: a set of direct attributes that are not forwarded to the inner
    #: handler.  This has to be extended as necessary.
    _direct_attrs = frozenset(['handler'])

    def __init__(self, handler):
        self.handler = handler

    def __getattr__(self, name):
        return getattr(self.handler, name)

    def __setattr__(self, name, value):
        if name in self._direct_attrs:
            return Handler.__setattr__(self, name, value)
        setattr(self.handler, name, value)


class StringFormatter(object):
    """Many handlers format the log entries to text format.  This is done
    by a callable that is passed a log record and returns an unicode
    string.  The default formatter for this is implemented as a class so
    that it becomes possible to hook into every aspect of the formatting
    process.
    """

    def __init__(self, format_string):
        self.format_string = format_string

    def _get_format_string(self):
        return self._format_string

    def _set_format_string(self, value):
        self._format_string = value
        self._formatter = value

    format_string = property(_get_format_string, _set_format_string)
    del _get_format_string, _set_format_string

    def format_record(self, record, handler):
        try:
            return self._formatter.format(record=record, handler=handler)
        except UnicodeEncodeError:
            # self._formatter is a str, but some of the record items
            # are unicode
            fmt = self._formatter.decode('ascii', 'replace')
            return fmt.format(record=record, handler=handler)
        except UnicodeDecodeError:
            # self._formatter is unicode, but some of the record items
            # are non-ascii str
            fmt = self._formatter.encode('ascii', 'replace')
            return fmt.format(record=record, handler=handler)

    def format_exception(self, record):
        return record.formatted_exception

    def __call__(self, record, handler):
        line = self.format_record(record, handler)
        exc = self.format_exception(record)
        if exc:
            line += u('\n') + exc
        return line


class StringFormatterHandlerMixin(object):
    """A mixin for handlers that provides a default integration for the
    :class:`~logbook.StringFormatter` class.  This is used for all handlers
    by default that log text to a destination.
    """

    #: a class attribute for the default format string to use if the
    #: constructor was invoked with `None`.
    default_format_string = DEFAULT_FORMAT_STRING

    #: the class to be used for string formatting
    formatter_class = StringFormatter

    def __init__(self, format_string):
        if format_string is None:
            format_string = self.default_format_string

        #: the currently attached format string as new-style format
        #: string.
        self.format_string = format_string

    def _get_format_string(self):
        if isinstance(self.formatter, StringFormatter):
            return self.formatter.format_string

    def _set_format_string(self, value):
        if value is None:
            self.formatter = None
        else:
            self.formatter = self.formatter_class(value)

    format_string = property(_get_format_string, _set_format_string)
    del _get_format_string, _set_format_string


class HashingHandlerMixin(object):
    """Mixin class for handlers that are hashing records."""

    def hash_record_raw(self, record):
        """Returns a hashlib object with the hash of the record."""
        hash = sha1()
        hash.update(('%d\x00' % record.level).encode('ascii'))
        hash.update((record.channel or u('')).encode('utf-8') + b('\x00'))
        hash.update(record.filename.encode('utf-8') + b('\x00'))
        hash.update(b(str(record.lineno)))
        return hash

    def hash_record(self, record):
        """Returns a hash for a record to keep it apart from other records.
        This is used for the `record_limit` feature.  By default
        The level, channel, filename and location are hashed.

        Calls into :meth:`hash_record_raw`.
        """
        return self.hash_record_raw(record).hexdigest()

_NUMBER_TYPES = integer_types + (float,)

class LimitingHandlerMixin(HashingHandlerMixin):
    """Mixin class for handlers that want to limit emitting records.

    In the default setting it delivers all log records but it can be set up
    to not send more than n mails for the same record each hour to not
    overload an inbox and the network in case a message is triggered multiple
    times a minute.  The following example limits it to 60 mails an hour::

        from datetime import timedelta
        handler = MailHandler(record_limit=1,
                              record_delta=timedelta(minutes=1))
    """

    def __init__(self, record_limit, record_delta):
        self.record_limit = record_limit
        self._limit_lock = new_fine_grained_lock()
        self._record_limits = {}
        if record_delta is None:
            record_delta = timedelta(seconds=60)
        elif isinstance(record_delta, _NUMBER_TYPES):
            record_delta = timedelta(seconds=record_delta)
        self.record_delta = record_delta

    def check_delivery(self, record):
        """Helper function to check if data should be delivered by this
        handler.  It returns a tuple in the form ``(suppression_count,
        allow)``.  The first one is the number of items that were not delivered
        so far, the second is a boolean flag if a delivery should happen now.
        """
        if self.record_limit is None:
            return 0, True
        hash = self.hash_record(record)
        self._limit_lock.acquire()
        try:
            allow_delivery = None
            suppression_count = old_count = 0
            first_count = now = datetime.utcnow()

            if hash in self._record_limits:
                last_count, suppression_count = self._record_limits[hash]
                if last_count + self.record_delta < now:
                    allow_delivery = True
                else:
                    first_count = last_count
                    old_count = suppression_count

            if not suppression_count and \
               len(self._record_limits) >= self.max_record_cache:
                cache_items = self._record_limits.items()
                cache_items.sort()
                del cache_items[:int(self._record_limits) \
                    * self.record_cache_prune]
                self._record_limits = dict(cache_items)

            self._record_limits[hash] = (first_count, old_count + 1)

            if allow_delivery is None:
                allow_delivery = old_count < self.record_limit
            return suppression_count, allow_delivery
        finally:
            self._limit_lock.release()


class StreamHandler(Handler, StringFormatterHandlerMixin):
    """a handler class which writes logging records, appropriately formatted,
    to a stream. note that this class does not close the stream, as sys.stdout
    or sys.stderr may be used.

    If a stream handler is used in a `with` statement directly it will
    :meth:`close` on exit to support this pattern::

        with StreamHandler(my_stream):
            pass

    .. admonition:: Notes on the encoding

       On Python 3, the encoding parameter is only used if a stream was
       passed that was opened in binary mode.
    """

    def __init__(self, stream, level=NOTSET, format_string=None,
                 encoding=None, filter=None, bubble=False):
        Handler.__init__(self, level, filter, bubble)
        StringFormatterHandlerMixin.__init__(self, format_string)
        self.encoding = encoding
        self.lock = new_fine_grained_lock()
        if stream is not _missing:
            self.stream = stream

    def __enter__(self):
        return Handler.__enter__(self)

    def __exit__(self, exc_type, exc_value, tb):
        self.close()
        return Handler.__exit__(self, exc_type, exc_value, tb)

    def ensure_stream_is_open(self):
        """this method should be overriden in sub-classes to ensure that the
        inner stream is open
        """
        pass

    def close(self):
        """The default stream handler implementation is not to close
        the wrapped stream but to flush it.
        """
        self.flush()

    def flush(self):
        """Flushes the inner stream."""
        if self.stream is not None and hasattr(self.stream, 'flush'):
            self.stream.flush()

    def encode(self, msg):
        """Encodes the message to the stream encoding."""
        stream = self.stream
        rv = msg + '\n'
        if (PY2 and is_unicode(rv)) or \
                not (PY2 or is_unicode(rv) or _is_text_stream(stream)):
            enc = self.encoding
            if enc is None:
                enc = getattr(stream, 'encoding', None) or 'utf-8'
            rv = rv.encode(enc, 'replace')
        return rv

    def write(self, item):
        """Writes a bytestring to the stream."""
        self.stream.write(item)

    def emit(self, record):
        msg = self.format(record)
        self.lock.acquire()
        try:
            self.ensure_stream_is_open()
            self.write(self.encode(msg))
            self.flush()
        finally:
            self.lock.release()


class FileHandler(StreamHandler):
    """A handler that does the task of opening and closing files for you.
    By default the file is opened right away, but you can also `delay`
    the open to the point where the first message is written.

    This is useful when the handler is used with a
    :class:`~logbook.FingersCrossedHandler` or something similar.
    """

    def __init__(self, filename, mode='a', encoding=None, level=NOTSET,
                 format_string=None, delay=False, filter=None, bubble=False):
        if encoding is None:
            encoding = 'utf-8'
        StreamHandler.__init__(self, None, level, format_string,
                               encoding, filter, bubble)
        self._filename = filename
        self._mode = mode
        if delay:
            self.stream = None
        else:
            self._open()

    def _open(self, mode=None):
        if mode is None:
            mode = self._mode
        self.stream = open(self._filename, mode)

    def write(self, item):
        self.ensure_stream_is_open()
        if not PY2 and isinstance(item, bytes):
            self.stream.buffer.write(item)
        else:
            self.stream.write(item)

    def close(self):
        self.lock.acquire()
        try:
            if self.stream is not None:
                self.flush()
                self.stream.close()
                self.stream = None
        finally:
            self.lock.release()

    def encode(self, record):
        # encodes based on the stream settings, so the stream has to be
        # open at the time this function is called.
        self.ensure_stream_is_open()
        return StreamHandler.encode(self, record)

    def ensure_stream_is_open(self):
        if self.stream is None:
            self._open()


class MonitoringFileHandler(FileHandler):
    """A file handler that will check if the file was moved while it was
    open.  This might happen on POSIX systems if an application like
    logrotate moves the logfile over.

    Because of different IO concepts on Windows, this handler will not
    work on a windows system.
    """

    def __init__(self, filename, mode='a', encoding='utf-8', level=NOTSET,
                 format_string=None, delay=False, filter=None, bubble=False):
        FileHandler.__init__(self, filename, mode, encoding, level,
                             format_string, delay, filter, bubble)
        if os.name == 'nt':
            raise RuntimeError('MonitoringFileHandler '
                               'does not support Windows')
        self._query_fd()

    def _query_fd(self):
        if self.stream is None:
            self._last_stat = None, None
        else:
            try:
                st = os.stat(self._filename)
            except OSError:
                e = sys.exc_info()[1]
                if e.errno != 2:
                    raise
                self._last_stat = None, None
            else:
                self._last_stat = st[stat.ST_DEV], st[stat.ST_INO]

    def emit(self, record):
        msg = self.format(record)
        self.lock.acquire()
        try:
            last_stat = self._last_stat
            self._query_fd()
            if last_stat != self._last_stat and self.stream is not None:
                self.flush()
                self.stream.close()
                self.stream = None
            self.ensure_stream_is_open()
            self.write(self.encode(msg))
            self.flush()
            self._query_fd()
        finally:
            self.lock.release()


class StderrHandler(StreamHandler):
    """A handler that writes to what is currently at stderr.  At the first
    glace this appears to just be a :class:`StreamHandler` with the stream
    set to :data:`sys.stderr` but there is a difference: if the handler is
    created globally and :data:`sys.stderr` changes later, this handler will
    point to the current `stderr`, whereas a stream handler would still
    point to the old one.
    """

    def __init__(self, level=NOTSET, format_string=None, filter=None,
                 bubble=False):
        StreamHandler.__init__(self, _missing, level, format_string,
                               None, filter, bubble)

    @property
    def stream(self):
        return sys.stderr


class RotatingFileHandler(FileHandler):
    """This handler rotates based on file size.  Once the maximum size
    is reached it will reopen the file and start with an empty file
    again.  The old file is moved into a backup copy (named like the
    file, but with a ``.backupnumber`` appended to the file.  So if
    you are logging to ``mail`` the first backup copy is called
    ``mail.1``.)

    The default number of backups is 5.  Unlike a similar logger from
    the logging package, the backup count is mandatory because just
    reopening the file is dangerous as it deletes the log without
    asking on rollover.
    """

    def __init__(self, filename, mode='a', encoding='utf-8', level=NOTSET,
                 format_string=None, delay=False, max_size=1024 * 1024,
                 backup_count=5, filter=None, bubble=False):
        FileHandler.__init__(self, filename, mode, encoding, level,
                             format_string, delay, filter, bubble)
        self.max_size = max_size
        self.backup_count = backup_count
        assert backup_count > 0, 'at least one backup file has to be ' \
                                 'specified'

    def should_rollover(self, record, bytes):
        self.stream.seek(0, 2)
        return self.stream.tell() + bytes >= self.max_size

    def perform_rollover(self):
        self.stream.close()
        for x in xrange(self.backup_count - 1, 0, -1):
            src = '%s.%d' % (self._filename, x)
            dst = '%s.%d' % (self._filename, x + 1)
            try:
                rename(src, dst)
            except OSError:
                e = sys.exc_info()[1]
                if e.errno != errno.ENOENT:
                    raise
        rename(self._filename, self._filename + '.1')
        self._open('w')

    def emit(self, record):
        msg = self.format(record)
        self.lock.acquire()
        try:
            msg = self.encode(msg)
            if self.should_rollover(record, len(msg)):
                self.perform_rollover()
            self.write(msg)
            self.flush()
        finally:
            self.lock.release()


class TimedRotatingFileHandler(FileHandler):
    """This handler rotates based on dates.  It will name the file
    after the filename you specify and the `date_format` pattern.

    So for example if you configure your handler like this::

        handler = TimedRotatingFileHandler('/var/log/foo.log',
                                           date_format='%Y-%m-%d')

    The filenames for the logfiles will look like this::

        /var/log/foo-2010-01-10.log
        /var/log/foo-2010-01-11.log
        ...

    By default it will keep all these files around, if you want to limit
    them, you can specify a `backup_count`.
    """

    def __init__(self, filename, mode='a', encoding='utf-8', level=NOTSET,
                 format_string=None, date_format='%Y-%m-%d',
                 backup_count=0, filter=None, bubble=False):
        FileHandler.__init__(self, filename, mode, encoding, level,
                             format_string, True, filter, bubble)
        self.date_format = date_format
        self.backup_count = backup_count
        self._fn_parts = os.path.splitext(os.path.abspath(filename))
        self._filename = None

    def _get_timed_filename(self, datetime):
        return datetime.strftime('-' + self.date_format) \
                       .join(self._fn_parts)

    def should_rollover(self, record):
        fn = self._get_timed_filename(record.time)
        rv = self._filename is not None and self._filename != fn
        # remember the current filename.  In case rv is True, the rollover
        # performing function will already have the new filename
        self._filename = fn
        return rv

    def files_to_delete(self):
        """Returns a list with the files that have to be deleted when
        a rollover occours.
        """
        directory = os.path.dirname(self._filename)
        files = []
        for filename in os.listdir(directory):
            filename = os.path.join(directory, filename)
            if filename.startswith(self._fn_parts[0] + '-') and \
               filename.endswith(self._fn_parts[1]):
                files.append((os.path.getmtime(filename), filename))
        files.sort()
        return files[:-self.backup_count + 1] if self.backup_count > 1\
                else files[:]

    def perform_rollover(self):
        self.stream.close()
        if self.backup_count > 0:
            for time, filename in self.files_to_delete():
                os.remove(filename)
        self._open('w')

    def emit(self, record):
        msg = self.format(record)
        self.lock.acquire()
        try:
            if self.should_rollover(record):
                self.perform_rollover()
            self.write(self.encode(msg))
            self.flush()
        finally:
            self.lock.release()


class TestHandler(Handler, StringFormatterHandlerMixin):
    """Like a stream handler but keeps the values in memory.  This
    logger provides some ways to test for the records in memory.

    Example usage::

        def my_test():
            with logbook.TestHandler() as handler:
                logger.warn('A warning')
                assert logger.has_warning('A warning')
                ...
    """
    default_format_string = TEST_FORMAT_STRING

    def __init__(self, level=NOTSET, format_string=None, filter=None,
                 bubble=False):
        Handler.__init__(self, level, filter, bubble)
        StringFormatterHandlerMixin.__init__(self, format_string)
        #: captures the :class:`LogRecord`\s as instances
        self.records = []
        self._formatted_records = []
        self._formatted_record_cache = []

    def close(self):
        """Close all records down when the handler is closed."""
        for record in self.records:
            record.close()

    def emit(self, record):
        # keep records open because we will want to examine them after the
        # call to the emit function.  If we don't do that, the traceback
        # attribute and other things will already be removed.
        record.keep_open = True
        self.records.append(record)

    @property
    def formatted_records(self):
        """Captures the formatted log records as unicode strings."""
        if len(self._formatted_record_cache) != len(self.records) or \
           any(r1 != r2 for r1, r2 in
               zip(self.records, self._formatted_record_cache)):
            self._formatted_records = [self.format(r) for r in self.records]
            self._formatted_record_cache = list(self.records)
        return self._formatted_records

    @property
    def has_criticals(self):
        """`True` if any :data:`CRITICAL` records were found."""
        return any(r.level == CRITICAL for r in self.records)

    @property
    def has_errors(self):
        """`True` if any :data:`ERROR` records were found."""
        return any(r.level == ERROR for r in self.records)

    @property
    def has_warnings(self):
        """`True` if any :data:`WARNING` records were found."""
        return any(r.level == WARNING for r in self.records)

    @property
    def has_notices(self):
        """`True` if any :data:`NOTICE` records were found."""
        return any(r.level == NOTICE for r in self.records)

    @property
    def has_infos(self):
        """`True` if any :data:`INFO` records were found."""
        return any(r.level == INFO for r in self.records)

    @property
    def has_debugs(self):
        """`True` if any :data:`DEBUG` records were found."""
        return any(r.level == DEBUG for r in self.records)

    def has_critical(self, *args, **kwargs):
        """`True` if a specific :data:`CRITICAL` log record exists.

        See :ref:`probe-log-records` for more information.
        """
        kwargs['level'] = CRITICAL
        return self._test_for(*args, **kwargs)

    def has_error(self, *args, **kwargs):
        """`True` if a specific :data:`ERROR` log record exists.

        See :ref:`probe-log-records` for more information.
        """
        kwargs['level'] = ERROR
        return self._test_for(*args, **kwargs)

    def has_warning(self, *args, **kwargs):
        """`True` if a specific :data:`WARNING` log record exists.

        See :ref:`probe-log-records` for more information.
        """
        kwargs['level'] = WARNING
        return self._test_for(*args, **kwargs)

    def has_notice(self, *args, **kwargs):
        """`True` if a specific :data:`NOTICE` log record exists.

        See :ref:`probe-log-records` for more information.
        """
        kwargs['level'] = NOTICE
        return self._test_for(*args, **kwargs)

    def has_info(self, *args, **kwargs):
        """`True` if a specific :data:`INFO` log record exists.

        See :ref:`probe-log-records` for more information.
        """
        kwargs['level'] = INFO
        return self._test_for(*args, **kwargs)

    def has_debug(self, *args, **kwargs):
        """`True` if a specific :data:`DEBUG` log record exists.

        See :ref:`probe-log-records` for more information.
        """
        kwargs['level'] = DEBUG
        return self._test_for(*args, **kwargs)

    def _test_for(self, message=None, channel=None, level=None):
        def _match(needle, haystack):
            "Matches both compiled regular expressions and strings"
            if isinstance(needle, REGTYPE) and needle.search(haystack):
                return True
            if needle == haystack:
                return True
            return False
        for record in self.records:
            if level is not None and record.level != level:
                continue
            if channel is not None and record.channel != channel:
                continue
            if message is not None and not _match(message, record.message):
                continue
            return True
        return False


class MailHandler(Handler, StringFormatterHandlerMixin,
                  LimitingHandlerMixin):
    """A handler that sends error mails.  The format string used by this
    handler are the contents of the mail plus the headers.  This is handy
    if you want to use a custom subject or ``X-`` header::

        handler = MailHandler(format_string='''\
        Subject: {record.level_name} on My Application

        {record.message}
        {record.extra[a_custom_injected_record]}
        ''')

    This handler will always emit text-only mails for maximum portability and
    best performance.

    In the default setting it delivers all log records but it can be set up
    to not send more than n mails for the same record each hour to not
    overload an inbox and the network in case a message is triggered multiple
    times a minute.  The following example limits it to 60 mails an hour::

        from datetime import timedelta
        handler = MailHandler(record_limit=1,
                              record_delta=timedelta(minutes=1))

    The default timedelta is 60 seconds (one minute).

    The mail handler is sending mails in a blocking manner.  If you are not
    using some centralized system for logging these messages (with the help
    of ZeroMQ or others) and the logging system slows you down you can
    wrap the handler in a :class:`logbook.queues.ThreadedWrapperHandler`
    that will then send the mails in a background thread.

    .. versionchanged:: 0.3
       The handler supports the batching system now.
    """
    default_format_string = MAIL_FORMAT_STRING
    default_related_format_string = MAIL_RELATED_FORMAT_STRING
    default_subject = u('Server Error in Application')

    #: the maximum number of record hashes in the cache for the limiting
    #: feature.  Afterwards, record_cache_prune percent of the oldest
    #: entries are removed
    max_record_cache = 512

    #: the number of items to prune on a cache overflow in percent.
    record_cache_prune = 0.333

    def __init__(self, from_addr, recipients, subject=None,
                 server_addr=None, credentials=None, secure=None,
                 record_limit=None, record_delta=None, level=NOTSET,
                 format_string=None, related_format_string=None,
                 filter=None, bubble=False):
        Handler.__init__(self, level, filter, bubble)
        StringFormatterHandlerMixin.__init__(self, format_string)
        LimitingHandlerMixin.__init__(self, record_limit, record_delta)
        self.from_addr = from_addr
        self.recipients = recipients
        if subject is None:
            subject = self.default_subject
        self.subject = subject
        self.server_addr = server_addr
        self.credentials = credentials
        self.secure = secure
        if related_format_string is None:
            related_format_string = self.default_related_format_string
        self.related_format_string = related_format_string

    def _get_related_format_string(self):
        if isinstance(self.related_formatter, StringFormatter):
            return self.related_formatter.format_string
    def _set_related_format_string(self, value):
        if value is None:
            self.related_formatter = None
        else:
            self.related_formatter = self.formatter_class(value)
    related_format_string = property(_get_related_format_string,
                                    _set_related_format_string)
    del _get_related_format_string, _set_related_format_string

    def get_recipients(self, record):
        """Returns the recipients for a record.  By default the
        :attr:`recipients` attribute is returned for all records.
        """
        return self.recipients

    def message_from_record(self, record, suppressed):
        """Creates a new message for a record as email message object
        (:class:`email.message.Message`).  `suppressed` is the number
        of mails not sent if the `record_limit` feature is active.
        """
        from email.message import Message
        from email.header import Header
        msg = Message()
        msg.set_charset('utf-8')
        lineiter = iter(self.format(record).splitlines())
        for line in lineiter:
            if not line:
                break
            h, v = line.split(':', 1)
            # We could probably just encode everything. For the moment encode
            # only what really needed to avoid breaking a couple of tests.
            try:
                v.encode('ascii')
            except UnicodeEncodeError:
                msg[h.strip()] = Header(v.strip(), 'utf-8')
            else:
                msg[h.strip()] = v.strip()

        msg.replace_header('Content-Transfer-Encoding', '8bit')

        body = '\r\n'.join(lineiter)
        if suppressed:
            body += '\r\n\r\nThis message occurred additional %d ' \
                    'time(s) and was suppressed' % suppressed

        # inconsistency in Python 2.5
        # other versions correctly return msg.get_payload() as str
        if sys.version_info < (2, 6) and isinstance(body, unicode):
            body = body.encode('utf-8')

        msg.set_payload(body, 'UTF-8')
        return msg

    def format_related_record(self, record):
        """Used for format the records that led up to another record or
        records that are related into strings.  Used by the batch formatter.
        """
        return self.related_formatter(record, self)

    def generate_mail(self, record, suppressed=0):
        """Generates the final email (:class:`email.message.Message`)
        with headers and date.  `suppressed` is the number of mails
        that were not send if the `record_limit` feature is active.
        """
        from email.utils import formatdate
        msg = self.message_from_record(record, suppressed)
        msg['From'] = self.from_addr
        msg['Date'] = formatdate()
        return msg

    def collapse_mails(self, mail, related, reason):
        """When escaling or grouped mails are """
        if not related:
            return mail
        if reason == 'group':
            title = 'Other log records in the same group'
        else:
            title = 'Log records that led up to this one'
        mail.set_payload('%s\r\n\r\n\r\n%s:\r\n\r\n%s' % (
            mail.get_payload(),
            title,
            '\r\n\r\n'.join(body.rstrip() for body in related)
        ))
        return mail

    def get_connection(self):
        """Returns an SMTP connection.  By default it reconnects for
        each sent mail.
        """
        from smtplib import SMTP, SMTP_PORT, SMTP_SSL_PORT
        if self.server_addr is None:
            host = '127.0.0.1'
            port = self.secure and SMTP_SSL_PORT or SMTP_PORT
        else:
            host, port = self.server_addr
        con = SMTP()
        con.connect(host, port)
        if self.credentials is not None:
            if self.secure is not None:
                con.ehlo()
                con.starttls(*self.secure)
                con.ehlo()
            con.login(*self.credentials)
        return con

    def close_connection(self, con):
        """Closes the connection that was returned by
        :meth:`get_connection`.
        """
        try:
            if con is not None:
                con.quit()
        except Exception:
            pass

    def deliver(self, msg, recipients):
        """Delivers the given message to a list of recpients."""
        con = self.get_connection()
        try:
            con.sendmail(self.from_addr, recipients, msg.as_string())
        finally:
            self.close_connection(con)

    def emit(self, record):
        suppressed = 0
        if self.record_limit is not None:
            suppressed, allow_delivery = self.check_delivery(record)
            if not allow_delivery:
                return
        self.deliver(self.generate_mail(record, suppressed),
                     self.get_recipients(record))

    def emit_batch(self, records, reason):
        if reason not in ('escalation', 'group'):
            raise RuntimeError("reason must be either 'escalation' or 'group'")
        records = list(records)
        if not records:
            return

        trigger = records.pop(reason == 'escalation' and -1 or 0)
        suppressed = 0
        if self.record_limit is not None:
            suppressed, allow_delivery = self.check_delivery(trigger)
            if not allow_delivery:
                return

        trigger_mail = self.generate_mail(trigger, suppressed)
        related = [self.format_related_record(record)
                   for record in records]

        self.deliver(self.collapse_mails(trigger_mail, related, reason),
                     self.get_recipients(trigger))


class GMailHandler(MailHandler):
    """
    A customized mail handler class for sending emails via GMail (or Google Apps mail)::

       handler = GMailHandler("my_user@gmail.com", "mypassword", ["to_user@some_mail.com"], ...) # other arguments same as MailHandler

    .. versionadded:: 0.6.0
    """

    def __init__(self, account_id, password, recipients, **kw):
        super(GMailHandler, self).__init__(
            account_id, recipients, secure=(), server_addr=("smtp.gmail.com", 587),
            credentials=(account_id, password), **kw)


class SyslogHandler(Handler, StringFormatterHandlerMixin):
    """A handler class which sends formatted logging records to a
    syslog server.  By default it will send to it via unix socket.
    """
    default_format_string = SYSLOG_FORMAT_STRING

    # priorities
    LOG_EMERG     = 0       #  system is unusable
    LOG_ALERT     = 1       #  action must be taken immediately
    LOG_CRIT      = 2       #  critical conditions
    LOG_ERR       = 3       #  error conditions
    LOG_WARNING   = 4       #  warning conditions
    LOG_NOTICE    = 5       #  normal but significant condition
    LOG_INFO      = 6       #  informational
    LOG_DEBUG     = 7       #  debug-level messages

    # facility codes
    LOG_KERN      = 0       #  kernel messages
    LOG_USER      = 1       #  random user-level messages
    LOG_MAIL      = 2       #  mail system
    LOG_DAEMON    = 3       #  system daemons
    LOG_AUTH      = 4       #  security/authorization messages
    LOG_SYSLOG    = 5       #  messages generated internally by syslogd
    LOG_LPR       = 6       #  line printer subsystem
    LOG_NEWS      = 7       #  network news subsystem
    LOG_UUCP      = 8       #  UUCP subsystem
    LOG_CRON      = 9       #  clock daemon
    LOG_AUTHPRIV  = 10      #  security/authorization messages (private)
    LOG_FTP       = 11      #  FTP daemon

    # other codes through 15 reserved for system use
    LOG_LOCAL0    = 16      #  reserved for local use
    LOG_LOCAL1    = 17      #  reserved for local use
    LOG_LOCAL2    = 18      #  reserved for local use
    LOG_LOCAL3    = 19      #  reserved for local use
    LOG_LOCAL4    = 20      #  reserved for local use
    LOG_LOCAL5    = 21      #  reserved for local use
    LOG_LOCAL6    = 22      #  reserved for local use
    LOG_LOCAL7    = 23      #  reserved for local use

    facility_names = {
        'auth':     LOG_AUTH,
        'authpriv': LOG_AUTHPRIV,
        'cron':     LOG_CRON,
        'daemon':   LOG_DAEMON,
        'ftp':      LOG_FTP,
        'kern':     LOG_KERN,
        'lpr':      LOG_LPR,
        'mail':     LOG_MAIL,
        'news':     LOG_NEWS,
        'syslog':   LOG_SYSLOG,
        'user':     LOG_USER,
        'uucp':     LOG_UUCP,
        'local0':   LOG_LOCAL0,
        'local1':   LOG_LOCAL1,
        'local2':   LOG_LOCAL2,
        'local3':   LOG_LOCAL3,
        'local4':   LOG_LOCAL4,
        'local5':   LOG_LOCAL5,
        'local6':   LOG_LOCAL6,
        'local7':   LOG_LOCAL7,
    }

    level_priority_map = {
        DEBUG:      LOG_DEBUG,
        INFO:       LOG_INFO,
        NOTICE:     LOG_NOTICE,
        WARNING:    LOG_WARNING,
        ERROR:      LOG_ERR,
        CRITICAL:   LOG_CRIT
    }

    def __init__(self, application_name=None, address=None,
                 facility='user', socktype=socket.SOCK_DGRAM,
                 level=NOTSET, format_string=None, filter=None,
                 bubble=False):
        Handler.__init__(self, level, filter, bubble)
        StringFormatterHandlerMixin.__init__(self, format_string)
        self.application_name = application_name

        if address is None:
            if sys.platform == 'darwin':
                address = '/var/run/syslog'
            else:
                address = '/dev/log'

        self.address = address
        self.facility = facility
        self.socktype = socktype

        if isinstance(address, string_types):
            self._connect_unixsocket()
        else:
            self._connect_netsocket()

    def _connect_unixsocket(self):
        self.unixsocket = True
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        try:
            self.socket.connect(self.address)
        except socket.error:
            self.socket.close()
            self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.socket.connect(self.address)

    def _connect_netsocket(self):
        self.unixsocket = False
        self.socket = socket.socket(socket.AF_INET, self.socktype)
        if self.socktype == socket.SOCK_STREAM:
            self.socket.connect(self.address)
            self.address = self.socket.getsockname()

    def encode_priority(self, record):
        facility = self.facility_names[self.facility]
        priority = self.level_priority_map.get(record.level,
                                               self.LOG_WARNING)
        return (facility << 3) | priority

    def emit(self, record):
        prefix = u('')
        if self.application_name is not None:
            prefix = self.application_name + u(':')
        self.send_to_socket((u('<%d>%s%s\x00') % (
            self.encode_priority(record),
            prefix,
            self.format(record)
        )).encode('utf-8'))

    def send_to_socket(self, data):
        if self.unixsocket:
            try:
                self.socket.send(data)
            except socket.error:
                self._connect_unixsocket()
                self.socket.send(data)
        elif self.socktype == socket.SOCK_DGRAM:
            # the flags are no longer optional on Python 3
            self.socket.sendto(data, 0, self.address)
        else:
            self.socket.sendall(data)

    def close(self):
        self.socket.close()


class NTEventLogHandler(Handler, StringFormatterHandlerMixin):
    """A handler that sends to the NT event log system."""
    dllname = None
    default_format_string = NTLOG_FORMAT_STRING

    def __init__(self, application_name, log_type='Application',
                 level=NOTSET, format_string=None, filter=None,
                 bubble=False):
        Handler.__init__(self, level, filter, bubble)
        StringFormatterHandlerMixin.__init__(self, format_string)

        if os.name != 'nt':
            raise RuntimeError('NTLogEventLogHandler requires a Windows '
                               'operating system.')

        try:
            import win32evtlogutil
            import win32evtlog
        except ImportError:
            raise RuntimeError('The pywin32 library is required '
                               'for the NTEventLogHandler.')

        self.application_name = application_name
        self._welu = win32evtlogutil
        dllname = self.dllname
        if not dllname:
            dllname = os.path.join(os.path.dirname(self._welu.__file__),
                                   '../win32service.pyd')
        self.log_type = log_type
        self._welu.AddSourceToRegistry(self.application_name, dllname,
                                       log_type)

        self._default_type = win32evtlog.EVENTLOG_INFORMATION_TYPE
        self._type_map = {
            DEBUG:      win32evtlog.EVENTLOG_INFORMATION_TYPE,
            INFO:       win32evtlog.EVENTLOG_INFORMATION_TYPE,
            NOTICE:     win32evtlog.EVENTLOG_INFORMATION_TYPE,
            WARNING:    win32evtlog.EVENTLOG_WARNING_TYPE,
            ERROR:      win32evtlog.EVENTLOG_ERROR_TYPE,
            CRITICAL:   win32evtlog.EVENTLOG_ERROR_TYPE
        }

    def unregister_logger(self):
        """Removes the application binding from the registry.  If you call
        this, the log viewer will no longer be able to provide any
        information about the message.
        """
        self._welu.RemoveSourceFromRegistry(self.application_name,
                                            self.log_type)

    def get_event_type(self, record):
        return self._type_map.get(record.level, self._default_type)

    def get_event_category(self, record):
        return 0

    def get_message_id(self, record):
        return 1

    def emit(self, record):
        id = self.get_message_id(record)
        cat = self.get_event_category(record)
        type = self.get_event_type(record)
        self._welu.ReportEvent(self.application_name, id, cat, type,
                               [self.format(record)])


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
        from logbook import FingersCrossedHandler

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

    Please keep in mind that the :class:`~logbook.FingersCrossedHandler`
    handler is a one-time handler.  Once triggered, it will not reset.  Because
    of that you will have to re-create it whenever you bind it.  In this case
    the handler is created when it's bound to the thread.

    Due to how the handler is implemented, the filter, bubble and level
    flags of the wrapped handler are ignored.

    .. versionchanged:: 0.3

    The default behaviour is to buffer up records and then invoke another
    handler when a severity theshold was reached with the buffer emitting.
    This now enables this logger to be properly used with the
    :class:`~logbook.MailHandler`.  You will now only get one mail for
    each buffered record.  However once the threshold was reached you would
    still get a mail for each record which is why the `reset` flag was added.

    When set to `True`, the handler will instantly reset to the untriggered
    state and start buffering again::

        handler = FingersCrossedHandler(MailHandler(...),
                                        buffer_size=10,
                                        reset=True)

    .. versionadded:: 0.3
       The `reset` flag was added.
    """

    #: the reason to be used for the batch emit.  The default is
    #: ``'escalation'``.
    #:
    #: .. versionadded:: 0.3
    batch_emit_reason = 'escalation'

    def __init__(self, handler, action_level=ERROR, buffer_size=0,
                 pull_information=True, reset=False, filter=None,
                 bubble=False):
        Handler.__init__(self, NOTSET, filter, bubble)
        self.lock = new_fine_grained_lock()
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
        self._reset = reset

    def close(self):
        if self._handler is not None:
            self._handler.close()

    def enqueue(self, record):
        if self._pull_information:
            record.pull_information()
        if self._action_triggered:
            self._handler.emit(record)
        else:
            self.buffered_records.append(record)
            if self._buffer_full:
                self.buffered_records.popleft()
            elif self.buffer_size and \
                 len(self.buffered_records) >= self.buffer_size:
                self._buffer_full = True
            return record.level >= self._level
        return False

    def rollover(self, record):
        if self._handler is None:
            self._handler = self._handler_factory(record, self)
        self._handler.emit_batch(iter(self.buffered_records), 'escalation')
        self.buffered_records.clear()
        self._action_triggered = not self._reset

    @property
    def triggered(self):
        """This attribute is `True` when the action was triggered.  From
        this point onwards the finger crossed handler transparently
        forwards all log records to the inner handler.  If the handler resets
        itself this will always be `False`.
        """
        return self._action_triggered

    def emit(self, record):
        self.lock.acquire()
        try:
            if self.enqueue(record):
                self.rollover(record)
        finally:
            self.lock.release()


class GroupHandler(WrapperHandler):
    """A handler that buffers all messages until it is popped again and then
    forwards all messages to another handler.  This is useful if you for
    example have an application that does computations and only a result
    mail is required.  A group handler makes sure that only one mail is sent
    and not multiple.  Some other handles might support this as well, though
    currently none of the builtins do.

    Example::

        with GroupHandler(MailHandler(...)):
            # everything here ends up in the mail

    The :class:`GroupHandler` is implemented as a :class:`WrapperHandler`
    thus forwarding all attributes of the wrapper handler.

    Notice that this handler really only emit the records when the handler
    is popped from the stack.

    .. versionadded:: 0.3
    """
    _direct_attrs = frozenset(['handler', 'pull_information',
                               'buffered_records'])

    def __init__(self, handler, pull_information=True):
        WrapperHandler.__init__(self, handler)
        self.pull_information = pull_information
        self.buffered_records = []

    def rollover(self):
        self.handler.emit_batch(self.buffered_records, 'group')
        self.buffered_records = []

    def pop_application(self):
        Handler.pop_application(self)
        self.rollover()

    def pop_thread(self):
        Handler.pop_thread(self)
        self.rollover()

    def pop_greenlet(self):
        Handler.pop_greenlet(self)
        self.rollover()

    def emit(self, record):
        if self.pull_information:
            record.pull_information()
        self.buffered_records.append(record)
