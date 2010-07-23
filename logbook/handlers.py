# -*- coding: utf-8 -*-
"""
    logbook.handlers
    ~~~~~~~~~~~~~~~~

    The handler interface and builtin handlers.

    :copyright: (c) 2010 by Armin Ronacher, Georg Brandl.
    :license: BSD, see LICENSE for more details.
"""

from __future__ import with_statement

import os
import sys
import threading
import traceback
import codecs
import errno
from contextlib import contextmanager
from itertools import izip

from logbook.base import (CRITICAL, ERROR, WARNING, NOTICE, INFO, DEBUG, NOTSET,
                          _level_name_property, _missing, lookup_level)
from logbook.helpers import rename


_global_handlers = []
_context_handler_lock = threading.Lock()
_context_handlers = threading.local()


DEFAULT_FORMAT_STRING = (
    u'[{record.time:%Y-%m-%d %H:%M}] '
    u'{record.level_name}: {record.logger_name}: {record.message}'
)
TEST_FORMAT_STRING = \
u'[{record.level_name}] {record.logger_name}: {record.message}'
MAIL_FORMAT_STRING = u'''\
Subject: {handler.subject}

Message type:       {record.level_name}
Location:           {record.filename}:{record.lineno}
Module:             {record.module}
Function:           {record.func_name}
Time:               {record.time:%Y-%m-%d %H:%M:%S}

Message:

{record.message}
'''


def iter_context_handlers():
    """Returns an iterator for all active context and global handlers."""
    handlers = list(_global_handlers)
    handlers.extend(getattr(_context_handlers, 'stack', ()))
    return reversed(handlers)


class Handler(object):
    """Handler instances dispatch logging events to specific destinations.

    The base handler class. Acts as a placeholder which defines the Handler
    interface. Handlers can optionally use Formatter instances to format
    records as desired. By default, no formatter is specified; in this case,
    the 'raw' message as determined by record.message is logged.
    """

    def __init__(self, level=NOTSET):
        self.name = None
        self.level = lookup_level(level)
        self.formatter = None

    level_name = _level_name_property()

    def format(self, record):
        """Formats a record with the given formatter."""
        if self.formatter is None:
            return record.message
        return self.formatter(record, self)

    def should_handle(self, record):
        """Called before handling to check if the handler is interested
        in the record.  This information is used to do preprocessing and
        bubbling.
        """
        return record.level >= self.level

    def handle(self, record):
        """Emits and falls back."""
        try:
            self.emit(record)
        except Exception:
            self.handle_error(record, sys.exc_info())

    def emit(self, record):
        """Emit the specified logging record."""

    def close(self):
        """Tidy up any resources used by the handler."""

    def push_context(self, processor=None, bubble=True):
        """Push the handler for the current context."""
        with _context_handler_lock:
            item = self, processor, bubble
            stack = getattr(_context_handlers, 'stack', None)
            if stack is None:
                _context_handlers.stack = [item]
            else:
                stack.append(item)

    def pop_context(self):
        """Pop the handler from the current context."""
        with _context_handler_lock:
            stack = getattr(_context_handlers, 'stack', None)
            assert stack, 'no handlers on stack'
            popped = stack.pop()[0]
            assert popped is self, 'popped unexpected handler'

    def push_global(self, processor=None, bubble=True):
        """Push the handler to the global stack."""
        _global_handlers.append((self, processor, bubble))

    def pop_global(self):
        """Pop the handler from the global stack."""
        assert _global_handlers, 'no handlers on global stack'
        popped = _global_handlers.pop()[0]
        assert popped is self, 'popped unexpected handler'

    @contextmanager
    def contextbound(self, processor=None, bubble=True):
        self.push_context(processor, bubble)
        try:
            yield
        finally:
            self.pop_context()

    @contextmanager
    def applicationbound(self, processor=None, bubble=True):
        self.push_global(processor, bubble)
        try:
            yield
        finally:
            self.pop_global()

    def handle_error(self, record, exc_info):
        """Handle errors which occur during an emit() call."""
        try:
            traceback.print_exception(*(exc_info + (None, sys.stderr)))
            sys.stderr.write('Logged from file %s, line %s\n' % (
                             record.filename, record.lineno))
        except IOError:
            pass


class StringFormatter(object):
    """Many handlers format the log entries to text format.  This is done
    by a callable that is passed a log record and returns an unicode
    string.  The default formatter for this is implemented as a class so
    that it becomes possible to hook into every aspect of the formatting
    process.
    """

    def __init__(self, format_string):
        self.format_string = format_string

    def format_record(self, record, handler):
        return self.format_string.format(record=record, handler=handler)

    def format_exception(self, record):
        return record.format_exception()

    def __call__(self, record, handler):
        line = self.format_record(record, handler)
        exc = self.format_exception(record)
        if exc:
            line += u'\n' + exc
        return line


class StringFormatterHandlerMixin(object):
    """A mixin for handlers that provides a default integration for the
    StringFormatter class.  This is used for all handlers by default that
    log text to a destination.
    """

    default_format_string = DEFAULT_FORMAT_STRING

    def __init__(self, format_string):
        if format_string is None:
            format_string = self.default_format_string
        self.format_string = format_string

    def _get_format_string(self):
        if isinstance(self.formatter, StringFormatter):
            return self.formatter.format_string
    def _set_format_string(self, value):
        self.formatter = StringFormatter(value)
    format_string = property(_get_format_string, _set_format_string)
    del _get_format_string, _set_format_string


class StreamHandler(Handler, StringFormatterHandlerMixin):
    """a handler class which writes logging records, appropriately formatted,
    to a stream. note that this class does not close the stream, as sys.stdout
    or sys.stderr may be used.
    """

    def __init__(self, stream, level=NOTSET, format_string=None):
        Handler.__init__(self, level)
        StringFormatterHandlerMixin.__init__(self, format_string)
        self.lock = threading.RLock()
        if stream is not _missing:
            self.stream = stream

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, tb):
        self.close()

    def close(self):
        # do not close the stream as we didn't open it ourselves, but at least
        # flush
        self.flush()

    def flush(self):
        """Flushes the stream."""
        if self.stream is not None and hasattr(self.stream, 'flush') \
           and not self.stream.closed:
            self.stream.flush()

    def format_and_encode(self, record):
        msg = self.format(record)
        enc = getattr(self.stream, 'encoding', None) or 'utf-8'
        return ('%s\n' % msg).encode(enc, 'replace')

    def write(self, item):
        self.stream.write(item)

    def emit(self, record):
        with self.lock:
            self.write(self.format_and_encode(record))
            self.flush()


class FileHandler(StreamHandler):
    """A handler that does the task of opening and closing files for you."""

    def __init__(self, filename, mode='a', encoding=None, level=NOTSET,
                 format_string=None, delay=False):
        StreamHandler.__init__(self, None, level, format_string)
        self._filename = filename
        self._mode = mode
        self._encoding = encoding
        if delay:
            self.stream = None
        else:
            self._open()

    def _open(self, mode=None):
        if mode is None:
            mode = self._mode
        if self._encoding is not None:
            self.stream = open(self._filename, mode)
        else:
            self.stream = codecs.open(self._filename, mode, self._encoding)

    def write(self, item):
        if self.stream is None:
            self._open()
        StreamHandler.write(self, item)

    def close(self):
        if self.stream is not None:
            self.flush()
            self.stream.close()

    def emit(self, record):
        if self.stream is None:
            self._open()
        StreamHandler.emit(self, record)


class StderrHandler(StreamHandler):
    """A handler that writes to what is currently at stderr."""

    def __init__(self, level=NOTSET, format_string=None):
        StreamHandler.__init__(self, _missing, level, format_string)

    @property
    def stream(self):
        return sys.stderr


class RotatingFileHandlerBase(FileHandler):
    """Baseclass for rotating file handlers."""

    def emit(self, record):
        with self.lock:
            msg = self.format_and_encode(record)
            if self.should_rollover(record, len(msg)):
                self.perform_rollover()
            self.write(msg)
            self.flush()


class RotatingFileHandler(RotatingFileHandlerBase):
    """This handler rotates based on file size."""

    def __init__(self, filename, mode='a', encoding=None, level=NOTSET,
                 format_string=None, delay=False, max_size=1024 * 1024,
                 backup_count=0):
        RotatingFileHandlerBase.__init__(self, filename, mode, encoding, level,
                                         format_string, delay)
        self.max_size = max_size
        self.backup_count = backup_count

    def should_rollover(self, record, bytes):
        self.stream.seek(0, 2)
        return self.stream.tell() + bytes >= self.max_size

    def perform_rollover(self):
        self.stream.close()
        if self.backup_count > 0:
            for x in xrange(self.backup_count - 1, 0, -1):
                src = '%s.%d' % (self._filename, x)
                dst = '%s.%d' % (self._filename, x + 1)
                try:
                    rename(src, dst)
                except OSError, e:
                    if e.errno != errno.ENOENT:
                        raise
            rename(self._filename, self._filename + '.1')
        self._open('w')


class TimedRotatingFileHandler(RotatingFileHandlerBase):
    """This handler rotates based on dates."""

    def __init__(self, filename, mode='a', encoding=None, level=NOTSET,
                 format_string=None, date_format='%Y-%m-%d',
                 backup_count=0):
        RotatingFileHandlerBase.__init__(self, filename, mode, encoding, level,
                                         format_string, True)
        self.date_format = date_format
        self.backup_count = backup_count
        self._fn_parts = os.path.splitext(os.path.abspath(filename))
        self._filename = None

    def _get_timed_filename(self, datetime):
        return datetime.strftime('-' + self.date_format) \
                       .join(self._fn_parts)

    def should_rollover(self, record, bytes):
        fn = self._get_timed_filename(record.time)
        rv = self._filename is not None and self._filename != fn
        # remember the current filename.  In case rv is True, the rollover
        # performing function will already have the new filename
        self._filename = fn
        return rv

    def files_to_delete(self):
        directory = os.path.dirname(self._filename)
        files = []
        for filename in os.listdir(directory):
            filename = os.path.join(directory, filename)
            if filename.startswith(self._fn_parts[0] + '-') and \
               filename.endswith(self._fn_parts[1]):
                files.append((os.path.getmtime(filename), filename))
        files.sort()
        return files[:-self.backup_count + 1]

    def perform_rollover(self):
        self.stream.close()
        if self.backup_count > 0:
            for time, filename in self.files_to_delete():
                os.remove(filename)
        self._open('w')


class TestHandler(Handler, StringFormatterHandlerMixin):
    """Like a stream handler but keeps the values in memory."""
    default_format_string = TEST_FORMAT_STRING

    def __init__(self, level=NOTSET, format_string=None):
        Handler.__init__(self, level)
        StringFormatterHandlerMixin.__init__(self, format_string)
        self.records = []
        self._formatted_records = []
        self._formatted_record_cache = []

    def emit(self, record):
        self.records.append(record)

    @property
    def formatted_records(self):
        if len(self._formatted_records) != self.records or \
           any(r1 != r2 for r1, (r2, f) in
               izip(self.records, self._formatted_records)):
            self._formatted_records = map(self.format, self.records)
            self._formatted_record_cache = list(self.records)
        return self._formatted_records

    @property
    def has_criticals(self):
        return any(r.level == CRITICAL for r in self.records)

    @property
    def has_errors(self):
        return any(r.level == ERROR for r in self.records)

    @property
    def has_warnings(self):
        return any(r.level == WARNING for r in self.records)

    @property
    def has_notices(self):
        return any(r.level == NOTICE for r in self.records)

    @property
    def has_infos(self):
        return any(r.level == INFO for r in self.records)

    @property
    def has_debugs(self):
        return any(r.level == DEBUG for r in self.records)

    def has_critical(self, *args, **kwargs):
        kwargs['level'] = CRITICAL
        return self._test_for(*args, **kwargs)

    def has_error(self, *args, **kwargs):
        kwargs['level'] = ERROR
        return self._test_for(*args, **kwargs)

    def has_warning(self, *args, **kwargs):
        kwargs['level'] = WARNING
        return self._test_for(*args, **kwargs)

    def has_notice(self, *args, **kwargs):
        kwargs['level'] = NOTICE
        return self._test_for(*args, **kwargs)

    def has_info(self, *args, **kwargs):
        kwargs['level'] = INFO
        return self._test_for(*args, **kwargs)

    def has_debug(self, *args, **kwargs):
        kwargs['level'] = DEBUG
        return self._test_for(*args, **kwargs)

    def _test_for(self, message=None, logger_name=None, level=None):
        for record in self.records:
            if level is not None and record.level != level:
                continue
            if logger_name is not None and record.logger_name != logger_name:
                continue
            if message is not None and record.message != message:
                continue
            return True
        return False


class MailHandler(Handler, StringFormatterHandlerMixin):
    default_format_string = MAIL_FORMAT_STRING
    default_subject = u'Server Error in Application'

    def __init__(self, from_addr, recipients, subject=None,
                 server_addr=None, credentials=None, secure=None,
                 level=NOTSET, format_string=None):
        Handler.__init__(self, level)
        StringFormatterHandlerMixin.__init__(self, format_string)
        self.from_addr = from_addr
        self.recipients = recipients
        if subject is None:
            subject = self.default_subject
        self.subject = subject
        self.server_addr = server_addr
        self.credentials = credentials
        self.secure = secure

    def get_recipients(self, record):
        return self.recipients

    def message_from_record(self, record):
        from email.message import Message
        msg = Message()
        lineiter = iter(self.format(record).splitlines())
        for line in lineiter:
            if not line:
                break
            pieces = line.split(':', 1)
            msg.add_header(*[x.strip() for x in pieces])
        msg.set_payload('\r\n'.join(lineiter))
        return msg

    def generate_mail(self, record):
        from email.utils import formatdate
        msg = self.message_from_record(record)
        msg['From'] = self.from_addr
        msg['Date'] = formatdate()
        return msg

    def get_connection(self):
        from smtplib import SMTP, SMTP_PORT, SMTP_SSL_PORT
        if self.server_addr is None:
            host = ''
            port = SMTP_SSL_PORT if self.secure else SMTP_PORT
        else:
            host, port = self.server_addr
        con = SMTP(host, port)
        if self.credentials is not None:
            if self.secure is not None:
                con.ehlo()
                con.starttls(*self.secure)
                con.ehlo()
            con.login(*self.credentials)
        return con

    def close_connection(self, con):
        con.quit()

    def deliver(self, msg, recipients):
        con = self.get_connection()
        try:
            con.sendmail(self.from_addr, recipients, msg.as_string())
        finally:
            self.close_connection(con)

    def emit(self, record):
        self.deliver(self.generate_mail(record), self.get_recipients(record))
