# -*- coding: utf-8 -*-
"""
    logbook.handlers
    ~~~~~~~~~~~~~~~~

    The handler interface and builtin handlers.

    :copyright: (c) 2010 by Armin Ronacher, Georg Brandl.
    :license: BSD, see LICENSE for more details.
"""

import os
import sys
import stat
import errno
import codecs
import socket
import threading
import traceback
from itertools import izip

from logbook.base import CRITICAL, ERROR, WARNING, NOTICE, INFO, DEBUG, \
     NOTSET, level_name_property, _missing, lookup_level, \
     ContextObject
from logbook.helpers import rename


DEFAULT_FORMAT_STRING = (
    u'[{record.time:%Y-%m-%d %H:%M}] '
    u'{record.level_name}: {record.channel}: {record.message}'
)
SYSLOG_FORMAT_STRING = u'{record.channel}: {record.message}'
NTLOG_FORMAT_STRING = u'''\
Message Level: {record.level_name}
Location: {record.filename}:{record.lineno}
Module: {record.module}
Function: {record.func_name}
Exact Time: {record.time:%Y-%m-%d %H:%M:%S}

Event provided Message:

{record.message}
'''
TEST_FORMAT_STRING = \
u'[{record.level_name}] {record.channel}: {record.message}'
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

SYSLOG_PORT = 514


def create_syshandler(application_name, level=NOTSET):
    """Creates the handler the operating system provides.  On Unix systems
    this creates a :class:`SyslogHandler`, on Windows sytems it will
    create a :class:`NTEventLogHandler`.
    """
    if os.name == 'nt':
        return NTEventLogHandler(application_name, level=level)
    return SyslogHandler(application_name, level=level)


class Handler(ContextObject):
    """Handler instances dispatch logging events to specific destinations.

    The base handler class. Acts as a placeholder which defines the Handler
    interface. Handlers can optionally use Formatter instances to format
    records as desired. By default, no formatter is specified; in this case,
    the 'raw' message as determined by record.message is logged.

    To bind a handler you can use the :meth:`push_application` and
    :meth:`push_thread` methods.  This will push the handler on a stack of
    handlers.  To undo this, use the :meth:`pop_application` and
    :meth:`pop_thread` methods::

        handler = MyHandler()
        handler.push_application()
        # all here goes to that handler
        handler.pop_application()

    By default messages send to that handler will not go to a handler on
    an outer level on the stack, if handled.  This can be changed by
    setting bubbling to `True`.  This setup for example would not have
    any effect::

        handler = NullHandler(bubble=False)
        handler.push_application()

    Whereas this setup disables all logging for the application::

        handler = NullHandler()
        handler.push_application()

    There are also context managers to setup the handler for the duration
    of a `with`-block::

        with handler.applicationbound():
            ...

        with handler.threadbound():
            ...

    Because `threadbound` is a common operation, it is aliased to a with
    on the handler itself::

        with handler:
            ...
    """

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

    def __del__(self):
        try:
            self.close()
        except Exception:
            # del is also invoked when init fails, so we better just
            # ignore any exception that might be raised here
            pass

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

    def close(self):
        """Tidy up any resources used by the handler."""

    def handle_error(self, record, exc_info):
        """Handle errors which occur during an emit() call."""
        try:
            traceback.print_exception(*(exc_info + (None, sys.stderr)))
            sys.stderr.write('Logged from file %s, line %s\n' % (
                             record.filename, record.lineno))
        except IOError:
            pass


class NullHandler(Handler):
    """A handler that does nothing, meant to be inserted in a handler chain
    with ``bubble=False`` to stop further processing.
    """


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
        return record.formatted_exception

    def __call__(self, record, handler):
        line = self.format_record(record, handler)
        exc = self.format_exception(record)
        if exc:
            line += u'\n' + exc
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


class StreamHandler(Handler, StringFormatterHandlerMixin):
    """a handler class which writes logging records, appropriately formatted,
    to a stream. note that this class does not close the stream, as sys.stdout
    or sys.stderr may be used.

    If a stream handler is used in a `with` statement directly it will
    :meth:`close` on exit to support this pattern::

        with StreamHandler(my_stream):
            pass
    """

    def __init__(self, stream, level=NOTSET, format_string=None, filter=None,
                 bubble=False):
        Handler.__init__(self, level, filter, bubble)
        StringFormatterHandlerMixin.__init__(self, format_string)
        self.lock = threading.Lock()
        if stream is not _missing:
            self.stream = stream

    def __enter__(self):
        return Handler.__enter__(self)

    def __exit__(self, exc_type, exc_value, tb):
        self.close()
        return Handler.__exit__(self, exc_type, exc_value, tb)

    def close(self):
        """The default stream handler implementation is not to close
        the wrapped stream but to flush it.
        """
        self.flush()

    def flush(self):
        """Flushes the inner stream."""
        if self.stream is not None and hasattr(self.stream, 'flush'):
            self.stream.flush()

    def format_and_encode(self, record):
        """Formats the record and encodes it to the stream encoding."""
        enc = getattr(self.stream, 'encoding', None) or 'utf-8'
        return (self.format(record) + u'\n').encode(enc, 'replace')

    def write(self, item):
        """Writes a bytestring to the stream."""
        self.stream.write(item)

    def emit(self, record):
        with self.lock:
            self.write(self.format_and_encode(record))
            self.flush()


class FileHandler(StreamHandler):
    """A handler that does the task of opening and closing files for you.
    By default the file is opened right away, but you can also `delay`
    the open to the point where the first message is written.

    This is useful when the handler is used with a
    :class:`~logbook.more.FingersCrossedHandler` or something similar.
    """

    def __init__(self, filename, mode='a', encoding='utf-8', level=NOTSET,
                 format_string=None, delay=False, filter=None, bubble=False):
        StreamHandler.__init__(self, None, level, format_string, filter, bubble)
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
        self.stream = codecs.open(self._filename, mode, self._encoding)

    def write(self, item):
        if self.stream is None:
            self._open()
        StreamHandler.write(self, item)

    def close(self):
        if self.stream is not None:
            self.flush()
            self.stream.close()
            self.stream = None

    def emit(self, record):
        if self.stream is None:
            self._open()
        StreamHandler.emit(self, record)


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
            raise RuntimeError('MonitoringFileHandler does not support Windows')
        self._query_fd()

    def _query_fd(self):
        if self.stream is None:
            self._last_stat = None, None
        else:
            try:
                st = os.stat(self._filename)
            except OSError, e:
                if e.errno != 2:
                    raise
                self._last_stat = None, None
            else:
                self._last_stat = st[stat.ST_DEV], st[stat.ST_INO]

    def emit(self, record):
        last_stat = self._last_stat
        self._query_fd()
        if last_stat != self._last_stat:
            self.close()
        FileHandler.emit(self, record)
        self._query_fd()


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
                               filter, bubble)

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

    def should_rollover(self, record, bytes):
        """Called with the log record and the number of bytes that
        would be written into the file.  The method has then to
        return `True` if a rollover should happen or `False`
        otherwise.
        """
        return False

    def perform_rollover(self):
        """Called if :meth:`should_rollover` returns `True` and has
        to perform the actual rollover.
        """


class RotatingFileHandler(RotatingFileHandlerBase):
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
        RotatingFileHandlerBase.__init__(self, filename, mode, encoding, level,
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
            except OSError, e:
                if e.errno != errno.ENOENT:
                    raise
        rename(self._filename, self._filename + '.1')
        self._open('w')


class TimedRotatingFileHandler(RotatingFileHandlerBase):
    """This handler rotates based on dates.  It will name the file
    after the filename you specify and the `date_format` pattern.

    So for example if you configure your handler like this::

        handler = TimedRotatingFileHandler('/var/log/foo.log',
                                           date_formnat='%Y-%m-%d')

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
        RotatingFileHandlerBase.__init__(self, filename, mode, encoding, level,
                                         format_string, True, filter, bubble)
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
        return files[:-self.backup_count + 1]

    def perform_rollover(self):
        self.stream.close()
        if self.backup_count > 0:
            for time, filename in self.files_to_delete():
                os.remove(filename)
        self._open('w')


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

    def __init__(self, level=NOTSET, format_string=None, filter=None, bubble=False):
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
        if len(self._formatted_records) != self.records or \
           any(r1 != r2 for r1, (r2, f) in
               izip(self.records, self._formatted_records)):
            self._formatted_records = map(self.format, self.records)
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
        for record in self.records:
            if level is not None and record.level != level:
                continue
            if channel is not None and record.channel != channel:
                continue
            if message is not None and record.message != message:
                continue
            return True
        return False


class MailHandler(Handler, StringFormatterHandlerMixin):
    """A handler that sends error mails."""
    default_format_string = MAIL_FORMAT_STRING
    default_subject = u'Server Error in Application'

    def __init__(self, from_addr, recipients, subject=None,
                 server_addr=None, credentials=None, secure=None,
                 level=NOTSET, format_string=None, filter=None,
                 bubble=False):
        Handler.__init__(self, level, filter, bubble)
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
        try:
            if con is not None:
                con.quit()
        except Exception:
            pass

    def deliver(self, msg, recipients):
        con = self.get_connection()
        try:
            con.sendmail(self.from_addr, recipients, msg.as_string())
        finally:
            self.close_connection(con)

    def emit(self, record):
        self.deliver(self.generate_mail(record), self.get_recipients(record))


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

        if isinstance(address, basestring):
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
        prefix = ''
        if self.application_name is not None:
            prefix = self.application_name.encode('utf-8') + ':'
        message = self.format(record).encode('utf-8')
        self.send_to_socket('<%d>%s%s\x00' % (self.encode_priority(record),
                                              prefix, message))

    def send_to_socket(self, data):
        if self.unixsocket:
            try:
                self.socket.send(data)
            except socket.error:
                self._connect_unixsocket()
                self.socket.send(data)
        elif self.socktype == socket.SOCK_DGRAM:
            self.socket.sendto(data, self.address)
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
            import win32evtlogutil, win32evtlog
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
