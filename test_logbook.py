import logbook

import os
import re
import sys
import shutil
import unittest
import tempfile
import string
from random import randrange
from calendar import timegm
from itertools import izip
from contextlib import contextmanager
from cStringIO import StringIO


@contextmanager
def capture_stderr():
    old = sys.stderr
    sys.stderr = StringIO()
    try:
        yield sys.stderr
    finally:
        sys.stderr = old


def make_fake_mail_handler(**kwargs):
    class FakeMailHandler(logbook.MailHandler):
        mails = []
        def get_connection(self):
            return self
        def close_connection(self, con):
            pass
        def sendmail(self, fromaddr, recipients, mail):
            self.mails.append((fromaddr, recipients, mail))

    return FakeMailHandler('foo@example.com', ['bar@example.com'],
                           level=logbook.ERROR, **kwargs)


class LogbookTestCase(unittest.TestCase):

    def setUp(self):
        self.log = logbook.Logger('testlogger')


class BasicAPITestCase(LogbookTestCase):

    def test_basic_logging(self):
        handler = logbook.TestHandler()
        with handler.contextbound(bubble=False):
            self.log.warn('This is a warning.  Nice hah?')

        self.assert_(handler.has_warning('This is a warning.  Nice hah?'))
        self.assertEqual(handler.formatted_records, [
            '[WARNING] testlogger: This is a warning.  Nice hah?'
        ])

    def test_custom_logger(self):
        client_ip = '127.0.0.1'
        class CustomLogger(logbook.Logger):
            def process_record(self, record):
                record.extra['ip'] = client_ip

        custom_log = CustomLogger('awesome logger')
        handler = logbook.TestHandler(format_string=
            '[{record.level_name}] {record.logger_name}: '
            '{record.message} [{record.extra[ip]}]')

        with handler.contextbound(bubble=False):
            custom_log.warn('Too many sounds')
            self.log.warn('"Music" playing')

        self.assertEqual(handler.formatted_records, [
            '[WARNING] awesome logger: Too many sounds [127.0.0.1]',
            '[WARNING] testlogger: "Music" playing []'
        ])

    def test_formatting_exception(self):
        def make_record():
            return logbook.LogRecord('Test Logger', logbook.WARNING,
                                     'Hello {foo:invalid}',
                                     kwargs={'foo': 42},
                                     frame=sys._getframe())
        record = make_record()
        try:
            record.message
        except TypeError, e:
            errormsg = str(e)
        else:
            self.assertFalse('Expected exception')

        self.assert_('Could not format message with provided arguments: '
                     'Invalid conversion specification' in errormsg)
        self.assert_("msg='Hello {foo:invalid}'" in errormsg)
        self.assert_('args=()' in errormsg)
        self.assert_("kwargs={'foo': 42}" in errormsg)
        self.assert_(re.search('Happened in file .*test_logbook.py, '
                               'line \d+', errormsg))


class HandlerTestCase(LogbookTestCase):

    def setUp(self):
        LogbookTestCase.setUp(self)
        self.dirname = tempfile.mkdtemp()
        self.filename = os.path.join(self.dirname, 'log.tmp')

    def tearDown(self):
        shutil.rmtree(self.dirname)
        LogbookTestCase.tearDown(self)

    def test_file_handler(self):
        handler = logbook.FileHandler(self.filename, format_string=
            '{record.level_name}:{record.logger_name}:{record.message}')
        with handler.contextbound(bubble=False):
            self.log.warn('warning message')
        handler.close()
        with open(self.filename) as f:
            self.assertEqual(f.readline(),
                             'WARNING:testlogger:warning message\n')

    def test_file_handler_delay(self):
        handler = logbook.FileHandler(self.filename, format_string=
            '{record.level_name}:{record.logger_name}:{record.message}',
            delay=True)
        self.assertFalse(os.path.isfile(self.filename))
        with handler.contextbound(bubble=False):
            self.log.warn('warning message')
        handler.close()
        with open(self.filename) as f:
            self.assertEqual(f.readline(),
                             'WARNING:testlogger:warning message\n')

    def test_custom_formatter(self):
        def custom_format(record, handler):
            return record.level_name + ':' + record.message
        with logbook.FileHandler(self.filename) as handler:
            handler.formatter = custom_format
            with handler.contextbound(bubble=False):
                self.log.warn('Custom formatters are awesome')
        with open(self.filename) as f:
            self.assertEqual(f.readline(),
                             'WARNING:Custom formatters are awesome\n')

    def test_rotating_file_handler(self):
        basename = os.path.join(self.dirname, 'rot.log')
        handler = logbook.RotatingFileHandler(basename, max_size=2048,
                                              backup_count=3)
        handler.format_string = '{record.message}'
        with handler:
            with handler.contextbound(bubble=False):
                for c, x in izip(string.letters, xrange(32)):
                    self.log.warn(c * 256)
        files = [x for x in os.listdir(self.dirname)
                 if x.startswith('rot.log')]
        files.sort()

        self.assertEqual(files, ['rot.log', 'rot.log.1', 'rot.log.2',
                                 'rot.log.3'])
        with open(basename) as f:
            self.assertEqual(f.readline().rstrip(), 'C' * 256)
            self.assertEqual(f.readline().rstrip(), 'D' * 256)
            self.assertEqual(f.readline().rstrip(), 'E' * 256)
            self.assertEqual(f.readline().rstrip(), 'F' * 256)

    def test_timed_rotating_file_handler(self):
        basename = os.path.join(self.dirname, 'trot.log')
        handler = logbook.TimedRotatingFileHandler(basename, backup_count=3)
        handler.format_string = '[{record.time:%H:%M}] {record.message}'

        def fake_record(message, year, month, day, hour=0,
                        minute=0, second=0):
            lr = logbook.LogRecord('Test Logger', logbook.WARNING,
                                   message)
            lr.timestamp = timegm((year, month, day, hour, minute, second))
            return lr

        with handler:
            for x in xrange(10):
                handler.handle(fake_record('First One', 2010, 1, 5, x + 1))
            for x in xrange(20):
                handler.handle(fake_record('Second One', 2010, 1, 6, x + 1))
            for x in xrange(10):
                handler.handle(fake_record('Third One', 2010, 1, 7, x + 1))
            for x in xrange(20):
                handler.handle(fake_record('Last One', 2010, 1, 8, x + 1))

        files = [x for x in os.listdir(self.dirname) if x.startswith('trot')]
        files.sort()
        self.assertEqual(files, ['trot-2010-01-06.log', 'trot-2010-01-07.log',
                                 'trot-2010-01-08.log'])
        with open(os.path.join(self.dirname, 'trot-2010-01-08.log')) as f:
            self.assertEqual(f.readline().rstrip(), '[01:00] Last One')
            self.assertEqual(f.readline().rstrip(), '[02:00] Last One')
        with open(os.path.join(self.dirname, 'trot-2010-01-07.log')) as f:
            self.assertEqual(f.readline().rstrip(), '[01:00] Third One')
            self.assertEqual(f.readline().rstrip(), '[02:00] Third One')

    def test_mail_handler(self):
        handler = make_fake_mail_handler(subject=u'\xf8nicode')
        with capture_stderr() as fallback:
            with handler.contextbound(bubble=False):
                self.log.warn('This is not mailed')
                try:
                    1/0
                except Exception:
                    self.log.exception('This is unfortunate')

            self.assertEqual(len(handler.mails), 1)
            sender, receivers, mail = handler.mails[0]
            self.assertEqual(sender, handler.from_addr)
            self.assert_('=?utf-8?q?=C3=B8nicode?=' in mail)
            self.assert_(re.search('Message type:\s+ERROR', mail))
            self.assert_(re.search('Location:.*test_logbook.py', mail))
            self.assert_(re.search('Module:\s+%s' % __name__, mail))
            self.assert_(re.search('Function:\s+test_mail_handler', mail))
            self.assert_('Message:\r\n\r\nThis is unfortunate' in mail)
            self.assert_('\r\n\r\nTraceback' in mail)
            self.assert_('1/0' in mail)
            self.assert_('This is not mailed' in fallback.getvalue())

    def test_handler_processors(self):
        handler = make_fake_mail_handler(format_string='''\
Subject: Application Error for {record.extra[path]} [{record.extra[method]}]

Message type:       {record.level_name}
Location:           {record.filename}:{record.lineno}
Module:             {record.module}
Function:           {record.func_name}
Time:               {record.time:%Y-%m-%d %H:%M:%S}
Remote IP:          {record.extra[ip]}
Request:            {record.extra[path]} [{record.extra[method]}]

Message:

{record.message}
''')

        class Request(object):
            remote_addr = '127.0.0.1'
            method = 'GET'
            path = '/index.html'

        def handle_request(request):
            def inject_extra(record, handler):
                record.extra['ip'] = request.remote_addr
                record.extra['method'] = request.method
                record.extra['path'] = request.path

            with handler.contextbound(processor=inject_extra, bubble=False):
                try:
                    1/0
                except Exception:
                    self.log.exception('Exception happened during request')

        handle_request(Request())
        self.assertEqual(len(handler.mails), 1)
        mail = handler.mails[0][2]
        self.assert_('Subject: Application Error for /index.html [GET]' in mail)
        self.assert_('1/0' in mail)

    def test_custom_handling_test(self):
        class MyTestHandler(logbook.TestHandler):
            def should_handle(self, record):
                return record.extra.get('flag') == 'testing'
        class MyLogger(logbook.Logger):
            def process_record(self, record):
                record.extra['flag'] = 'testing'
        log = MyLogger()
        handler = MyTestHandler()
        with capture_stderr() as captured:
            with handler.contextbound(bubble=False):
                log.warn('From my logger')
                self.log.warn('From another logger')
            self.assert_(handler.has_warning('From my logger'))
            self.assert_('From another logger' in captured.getvalue())


class AttributeTestCase(LogbookTestCase):

    def test_level_properties(self):
        self.assertEqual(self.log.level, logbook.NOTSET)
        self.assertEqual(self.log.level_name, 'NOTSET')
        self.log.level_name = 'WARNING'
        self.assertEqual(self.log.level, logbook.WARNING)
        self.log.level = logbook.ERROR
        self.assertEqual(self.log.level_name, 'ERROR')

    def test_reflected_properties(self):
        group = logbook.LoggerGroup()
        group.add_logger(self.log)
        group.level = logbook.ERROR
        self.assertEqual(self.log.level, logbook.ERROR)
        self.assertEqual(self.log.level_name, 'ERROR')
        group.level = logbook.WARNING
        self.assertEqual(self.log.level, logbook.WARNING)
        self.assertEqual(self.log.level_name, 'WARNING')
        self.log.level = logbook.CRITICAL
        group.level = logbook.DEBUG
        self.assertEqual(self.log.level, logbook.CRITICAL)
        self.assertEqual(self.log.level_name, 'CRITICAL')


class DefaultConfigurationTestCase(LogbookTestCase):

    def test_default_handlers(self):
        with capture_stderr() as stream:
            self.log.warn('Aha!')
            captured = stream.getvalue()
        assert 'WARNING: testlogger: Aha!' in captured


class LoggingCompatTestCase(LogbookTestCase):

    def test_basic_compat(self):
        from logging import getLogger
        from logbook.compat import temporarily_redirected_logging

        name = 'test_logbook-%d' % randrange(1 << 32)
        logger = getLogger(name)
        with capture_stderr() as captured:
            with temporarily_redirected_logging():
                logger.warn('This is from the old system')
            self.assert_(('WARNING: %s: This is from the old system' % name)
                         in captured.getvalue())


class MoreTestCase(LogbookTestCase):

    def test_fingerscrossed(self):
        from logbook.more import FingersCrossedHandler
        handler = FingersCrossedHandler(logbook.default_handler,
                                        logbook.WARNING)

        # if no warning occurs, the infos are not logged
        with handler.contextbound(bubble=False):
            with capture_stderr() as captured:
                self.log.info('some info')
            self.assertEquals(captured.getvalue(), '')

        # but if it does, all log messages are output
        with handler.contextbound(bubble=False):
            with capture_stderr() as captured:
                self.log.info('some info')
                self.log.warning('something happened')
            logs = captured.getvalue()
            self.assert_('some info' in logs)
            self.assert_('something happened' in logs)

    def test_tagged(self):
        from logbook.more import TaggingLogger, TaggingHandler
        stream = StringIO()
        second_handler = logbook.StreamHandler(stream)

        logger = TaggingLogger('name', 'cmd')
        handler = TaggingHandler(
            info = logbook.default_handler,
            cmd = second_handler,
            all = [logbook.default_handler, second_handler],
        )

        with handler.contextbound(bubble=False):
            with capture_stderr() as captured:
                logger.log('info', 'info message')
                logger.log('all', 'all message')
                logger.cmd('cmd message')

        stderr = captured.getvalue()

        self.assert_('info message' in stderr)
        self.assert_('all message' in stderr)
        self.assert_('cmd message' not in stderr)

        stringio = stream.getvalue()

        self.assert_('info message' not in stringio)
        self.assert_('all message' in stringio)
        self.assert_('cmd message' in stringio)


if __name__ == '__main__':
    unittest.main()
