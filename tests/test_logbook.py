# -*- coding: utf-8 -*-
from .utils import (
    LogbookTestCase,
    activate_via_push_pop,
    activate_via_with_statement,
    capturing_stderr_context,
    get_total_delta_seconds,
    make_fake_mail_handler,
    missing,
    require_module,
    require_py3,
)
from contextlib import closing, contextmanager
from datetime import datetime, timedelta
from random import randrange
import logbook
from logbook.helpers import StringIO, xrange, iteritems, zip, u
import os
import pickle
import re
import shutil
import socket
import sys
import tempfile
import time
import json
try:
    from thread import get_ident
except ImportError:
    from _thread import get_ident

__file_without_pyc__ = __file__
if __file_without_pyc__.endswith(".pyc"):
    __file_without_pyc__ = __file_without_pyc__[:-1]

LETTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"

class _BasicAPITestCase(LogbookTestCase):
    def test_basic_logging(self):
        with self.thread_activation_strategy(logbook.TestHandler()) as handler:
            self.log.warn('This is a warning.  Nice hah?')

        self.assert_(handler.has_warning('This is a warning.  Nice hah?'))
        self.assertEqual(handler.formatted_records, [
            '[WARNING] testlogger: This is a warning.  Nice hah?'
        ])

    def test_extradict(self):
        with self.thread_activation_strategy(logbook.TestHandler()) as handler:
            self.log.warn('Test warning')
        record = handler.records[0]
        record.extra['existing'] = 'foo'
        self.assertEqual(record.extra['nonexisting'], '')
        self.assertEqual(record.extra['existing'], 'foo')
        self.assertEqual(repr(record.extra),
                         'ExtraDict({\'existing\': \'foo\'})')

    def test_custom_logger(self):
        client_ip = '127.0.0.1'

        class CustomLogger(logbook.Logger):
            def process_record(self, record):
                record.extra['ip'] = client_ip

        custom_log = CustomLogger('awesome logger')
        fmt = '[{record.level_name}] {record.channel}: ' \
              '{record.message} [{record.extra[ip]}]'
        handler = logbook.TestHandler(format_string=fmt)
        self.assertEqual(handler.format_string, fmt)

        with self.thread_activation_strategy(handler):
            custom_log.warn('Too many sounds')
            self.log.warn('"Music" playing')

        self.assertEqual(handler.formatted_records, [
            '[WARNING] awesome logger: Too many sounds [127.0.0.1]',
            '[WARNING] testlogger: "Music" playing []'
        ])

    def test_handler_exception(self):
        class ErroringHandler(logbook.TestHandler):
            def emit(self, record):
                raise RuntimeError('something bad happened')

        with capturing_stderr_context() as stderr:
            with self.thread_activation_strategy(ErroringHandler()) as handler:
                self.log.warn('I warn you.')
        self.assert_('something bad happened' in stderr.getvalue())
        self.assert_('I warn you' not in stderr.getvalue())

    def test_formatting_exception(self):
        def make_record():
            return logbook.LogRecord('Test Logger', logbook.WARNING,
                                     'Hello {foo:invalid}',
                                     kwargs={'foo': 42},
                                     frame=sys._getframe())
        record = make_record()
        with self.assertRaises(TypeError) as caught:
            record.message

        errormsg = str(caught.exception)
        self.assertRegexpMatches(errormsg,
                "Could not format message with provided arguments: Invalid (?:format specifier)|(?:conversion specification)|(?:format spec)")
        self.assertIn("msg='Hello {foo:invalid}'", errormsg)
        self.assertIn('args=()', errormsg)
        self.assertIn("kwargs={'foo': 42}", errormsg)
        self.assertRegexpMatches(
            errormsg,
            r'Happened in file .*%s, line \d+' % __file_without_pyc__)

    def test_exception_catching(self):
        logger = logbook.Logger('Test')
        with self.thread_activation_strategy(logbook.TestHandler()) as handler:
            self.assertFalse(handler.has_error())
            try:
                1 / 0
            except Exception:
                logger.exception()
            try:
                1 / 0
            except Exception:
                logger.exception('Awesome')
            self.assert_(handler.has_error('Uncaught exception occurred'))
            self.assert_(handler.has_error('Awesome'))
        self.assertIsNotNone(handler.records[0].exc_info)
        self.assertIn('1 / 0', handler.records[0].formatted_exception)

    def test_exc_info_tuple(self):
        self._test_exc_info(as_tuple=True)

    def test_exc_info_true(self):
        self._test_exc_info(as_tuple=False)

    def _test_exc_info(self, as_tuple):
        logger = logbook.Logger("Test")
        with self.thread_activation_strategy(logbook.TestHandler()) as handler:
            try:
                1 / 0
            except Exception:
                exc_info = sys.exc_info()
                logger.info("Exception caught", exc_info=exc_info if as_tuple else True)
        self.assertIsNotNone(handler.records[0].exc_info)
        self.assertEquals(handler.records[0].exc_info, exc_info)

    def test_exporting(self):
        with self.thread_activation_strategy(logbook.TestHandler()) as handler:
            try:
                1 / 0
            except Exception:
                self.log.exception()
            record = handler.records[0]

        exported = record.to_dict()
        record.close()
        imported = logbook.LogRecord.from_dict(exported)
        for key, value in iteritems(record.__dict__):
            if key[0] == '_':
                continue
            self.assertEqual(value, getattr(imported, key))

    def test_pickle(self):
        with self.thread_activation_strategy(logbook.TestHandler()) as handler:
            try:
                1 / 0
            except Exception:
                self.log.exception()
            record = handler.records[0]
        record.pull_information()
        record.close()

        for p in xrange(pickle.HIGHEST_PROTOCOL):
            exported = pickle.dumps(record, p)
            imported = pickle.loads(exported)
            for key, value in iteritems(record.__dict__):
                if key[0] == '_':
                    continue
                imported_value = getattr(imported, key)
                if isinstance(value, ZeroDivisionError):
                    # in Python 3.2, ZeroDivisionError(x) != ZeroDivisionError(x)
                    self.assert_(type(value) is type(imported_value))
                    self.assertEqual(value.args, imported_value.args)
                else:
                    self.assertEqual(value, imported_value)

    def test_timedate_format(self):
        """
        tests the logbook.set_datetime_format() function
        """
        FORMAT_STRING = '{record.time:%H:%M:%S} {record.message}'
        handler = logbook.TestHandler(format_string=FORMAT_STRING)
        handler.push_thread()
        logbook.set_datetime_format('utc')
        try:
            self.log.warn('This is a warning.')
            time_utc = handler.records[0].time
            logbook.set_datetime_format('local')
            self.log.warn('This is a warning.')
            time_local = handler.records[1].time
        finally:
            handler.pop_thread()
            # put back the default time factory
            logbook.set_datetime_format('utc')

        # get the expected difference between local and utc time
        t1 = datetime.now()
        t2 = datetime.utcnow()

        tz_minutes_diff = get_total_delta_seconds(t1 - t2)/60.0

        if abs(tz_minutes_diff) < 1:
            self.skipTest("Cannot test utc/localtime differences if they vary by less than one minute...")

        # get the difference between LogRecord local and utc times
        logbook_minutes_diff = get_total_delta_seconds(time_local - time_utc)/60.0
        self.assertGreater(abs(logbook_minutes_diff), 1, "Localtime does not differ from UTC by more than 1 minute (Local: %s, UTC: %s)" % (time_local, time_utc))

        ratio = logbook_minutes_diff / tz_minutes_diff

        self.assertGreater(ratio, 0.99)
        self.assertLess(ratio, 1.01)

class BasicAPITestCase_Regular(_BasicAPITestCase):
    def setUp(self):
        super(BasicAPITestCase_Regular, self).setUp()
        self.thread_activation_strategy = activate_via_with_statement

class BasicAPITestCase_Contextmgr(_BasicAPITestCase):
    def setUp(self):
        super(BasicAPITestCase_Contextmgr, self).setUp()
        self.thread_activation_strategy = activate_via_push_pop

class _HandlerTestCase(LogbookTestCase):
    def setUp(self):
        super(_HandlerTestCase, self).setUp()
        self.dirname = tempfile.mkdtemp()
        self.filename = os.path.join(self.dirname, 'log.tmp')

    def tearDown(self):
        shutil.rmtree(self.dirname)
        super(_HandlerTestCase, self).tearDown()

    def test_file_handler(self):
        handler = logbook.FileHandler(self.filename,
            format_string='{record.level_name}:{record.channel}:'
            '{record.message}',)
        with self.thread_activation_strategy(handler):
            self.log.warn('warning message')
        handler.close()
        with open(self.filename) as f:
            self.assertEqual(f.readline(),
                             'WARNING:testlogger:warning message\n')

    def test_file_handler_unicode(self):
        with capturing_stderr_context() as captured:
            with self.thread_activation_strategy(logbook.FileHandler(self.filename)) as h:
                self.log.info(u'\u0431')
        self.assertFalse(captured.getvalue())

    def test_file_handler_delay(self):
        handler = logbook.FileHandler(self.filename,
            format_string='{record.level_name}:{record.channel}:'
            '{record.message}', delay=True)
        self.assertFalse(os.path.isfile(self.filename))
        with self.thread_activation_strategy(handler):
            self.log.warn('warning message')
        handler.close()

        with open(self.filename) as f:
            self.assertEqual(f.readline(),
                             'WARNING:testlogger:warning message\n')

    def test_monitoring_file_handler(self):
        if os.name == "nt":
            self.skipTest("unsupported on windows due to different IO (also unneeded)")
        handler = logbook.MonitoringFileHandler(self.filename,
            format_string='{record.level_name}:{record.channel}:'
            '{record.message}', delay=True)
        with self.thread_activation_strategy(handler):
            self.log.warn('warning message')
            os.rename(self.filename, self.filename + '.old')
            self.log.warn('another warning message')
        handler.close()
        with open(self.filename) as f:
            self.assertEqual(f.read().strip(),
                             'WARNING:testlogger:another warning message')

    def test_custom_formatter(self):
        def custom_format(record, handler):
            return record.level_name + ':' + record.message
        handler = logbook.FileHandler(self.filename)
        with self.thread_activation_strategy(handler):
            handler.formatter = custom_format
            self.log.warn('Custom formatters are awesome')

        with open(self.filename) as f:
            self.assertEqual(f.readline(),
                             'WARNING:Custom formatters are awesome\n')

    def test_rotating_file_handler(self):
        basename = os.path.join(self.dirname, 'rot.log')
        handler = logbook.RotatingFileHandler(basename, max_size=2048,
                                              backup_count=3,
                                              )
        handler.format_string = '{record.message}'
        with self.thread_activation_strategy(handler):
            for c, x in zip(LETTERS, xrange(32)):
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
            lr.time = datetime(year, month, day, hour, minute, second)
            return lr

        with self.thread_activation_strategy(handler):
            for x in xrange(10):
                handler.handle(fake_record('First One', 2010, 1, 5, x + 1))
            for x in xrange(20):
                handler.handle(fake_record('Second One', 2010, 1, 6, x + 1))
            for x in xrange(10):
                handler.handle(fake_record('Third One', 2010, 1, 7, x + 1))
            for x in xrange(20):
                handler.handle(fake_record('Last One', 2010, 1, 8, x + 1))

        files = sorted(
            x for x in os.listdir(self.dirname) if x.startswith('trot')
        )
        self.assertEqual(files, ['trot-2010-01-06.log', 'trot-2010-01-07.log',
                                 'trot-2010-01-08.log'])
        with open(os.path.join(self.dirname, 'trot-2010-01-08.log')) as f:
            self.assertEqual(f.readline().rstrip(), '[01:00] Last One')
            self.assertEqual(f.readline().rstrip(), '[02:00] Last One')
        with open(os.path.join(self.dirname, 'trot-2010-01-07.log')) as f:
            self.assertEqual(f.readline().rstrip(), '[01:00] Third One')
            self.assertEqual(f.readline().rstrip(), '[02:00] Third One')

    def test_mail_handler(self):
        subject = u'\xf8nicode'
        handler = make_fake_mail_handler(subject=subject)
        with capturing_stderr_context() as fallback:
            with self.thread_activation_strategy(handler):
                self.log.warn('This is not mailed')
                try:
                    1 / 0
                except Exception:
                    self.log.exception(u'Viva la Espa\xf1a')

            if not handler.mails:
                # if sending the mail failed, the reason should be on stderr
                self.fail(fallback.getvalue())

            self.assertEqual(len(handler.mails), 1)
            sender, receivers, mail = handler.mails[0]
            mail = mail.replace("\r", "")
            self.assertEqual(sender, handler.from_addr)
            self.assert_('=?utf-8?q?=C3=B8nicode?=' in mail)
            self.assertRegexpMatches(mail, 'Message type:\s+ERROR')
            self.assertRegexpMatches(mail, 'Location:.*%s' % __file_without_pyc__)
            self.assertRegexpMatches(mail, 'Module:\s+%s' % __name__)
            self.assertRegexpMatches(mail, 'Function:\s+test_mail_handler')
            body = u'Message:\n\nViva la Espa\xf1a'
            if sys.version_info < (3, 0):
                body = body.encode('utf-8')
            self.assertIn(body, mail)
            self.assertIn('\n\nTraceback (most', mail)
            self.assertIn('1 / 0', mail)
            self.assertIn('This is not mailed', fallback.getvalue())

    def test_mail_handler_record_limits(self):
        suppression_test = re.compile('This message occurred additional \d+ '
                                      'time\(s\) and was suppressed').search
        handler = make_fake_mail_handler(record_limit=1,
                                         record_delta=timedelta(seconds=0.5))
        with self.thread_activation_strategy(handler):
            later = datetime.utcnow() + timedelta(seconds=1.1)
            while datetime.utcnow() < later:
                self.log.error('Over and over...')

            # first mail that is always delivered + 0.5 seconds * 2
            # and 0.1 seconds of room for rounding errors makes 3 mails
            self.assertEqual(len(handler.mails), 3)

            # first mail is always delivered
            self.assert_(not suppression_test(handler.mails[0][2]))

            # the next two have a supression count
            self.assert_(suppression_test(handler.mails[1][2]))
            self.assert_(suppression_test(handler.mails[2][2]))

    def test_mail_handler_batching(self):
        mail_handler = make_fake_mail_handler()
        handler = logbook.FingersCrossedHandler(mail_handler, reset=True)
        with self.thread_activation_strategy(handler):
            self.log.warn('Testing')
            self.log.debug('Even more')
            self.log.error('And this triggers it')
            self.log.info('Aha')
            self.log.error('And this triggers it again!')

        self.assertEqual(len(mail_handler.mails), 2)
        mail = mail_handler.mails[0][2]

        pieces = mail.split('Log records that led up to this one:')
        self.assertEqual(len(pieces), 2)
        body, rest = pieces
        rest = rest.replace("\r", "")

        self.assertRegexpMatches(body, 'Message type:\s+ERROR')
        self.assertRegexpMatches(body, 'Module:\s+%s' % __name__)
        self.assertRegexpMatches(body, 'Function:\s+test_mail_handler_batching')

        related = rest.strip().split('\n\n')
        self.assertEqual(len(related), 2)
        self.assertRegexpMatches(related[0], 'Message type:\s+WARNING')
        self.assertRegexpMatches(related[1], 'Message type:\s+DEBUG')

        self.assertIn('And this triggers it again', mail_handler.mails[1][2])

    def test_group_handler_mail_combo(self):
        mail_handler = make_fake_mail_handler(level=logbook.DEBUG)
        handler = logbook.GroupHandler(mail_handler)
        with self.thread_activation_strategy(handler):
            self.log.error('The other way round')
            self.log.warn('Testing')
            self.log.debug('Even more')
            self.assertEqual(mail_handler.mails, [])

        self.assertEqual(len(mail_handler.mails), 1)
        mail = mail_handler.mails[0][2]

        pieces = mail.split('Other log records in the same group:')
        self.assertEqual(len(pieces), 2)
        body, rest = pieces
        rest = rest.replace("\r", "")

        self.assertRegexpMatches(body, 'Message type:\s+ERROR')
        self.assertRegexpMatches(body, 'Module:\s+'+__name__)
        self.assertRegexpMatches(body, 'Function:\s+test_group_handler_mail_combo')

        related = rest.strip().split('\n\n')
        self.assertEqual(len(related), 2)
        self.assertRegexpMatches(related[0], 'Message type:\s+WARNING')
        self.assertRegexpMatches(related[1], 'Message type:\s+DEBUG')

    def test_syslog_handler(self):
        to_test = [
            (socket.AF_INET, ('127.0.0.1', 0)),
        ]
        if hasattr(socket, 'AF_UNIX'):
            to_test.append((socket.AF_UNIX, self.filename))
        for sock_family, address in to_test:
            with closing(socket.socket(sock_family, socket.SOCK_DGRAM)) as inc:
                inc.bind(address)
                inc.settimeout(1)
                for app_name in [None, 'Testing']:
                    handler = logbook.SyslogHandler(app_name, inc.getsockname())
                    with self.thread_activation_strategy(handler):
                        self.log.warn('Syslog is weird')
                    try:
                        rv = inc.recvfrom(1024)[0]
                    except socket.error:
                        self.fail('got timeout on socket')
                    self.assertEqual(rv, (
                        u'<12>%stestlogger: Syslog is weird\x00' %
                        (app_name and app_name + u':' or u'')).encode('utf-8'))

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
            def inject_extra(record):
                record.extra['ip'] = request.remote_addr
                record.extra['method'] = request.method
                record.extra['path'] = request.path

            processor = logbook.Processor(inject_extra)
            with self.thread_activation_strategy(processor):
                handler.push_thread()
                try:
                    try:
                        1 / 0
                    except Exception:
                        self.log.exception('Exception happened during request')
                finally:
                    handler.pop_thread()

        handle_request(Request())
        self.assertEqual(len(handler.mails), 1)
        mail = handler.mails[0][2]
        self.assertIn('Subject: Application Error '
                     'for /index.html [GET]', mail)
        self.assertIn('1 / 0', mail)

    def test_regex_matching(self):
        test_handler = logbook.TestHandler()
        with self.thread_activation_strategy(test_handler):
            self.log.warn('Hello World!')
            self.assert_(test_handler.has_warning(re.compile('^Hello')))
            self.assert_(not test_handler.has_warning(re.compile('world$')))
            self.assert_(not test_handler.has_warning('^Hello World'))

    def test_custom_handling_test(self):
        class MyTestHandler(logbook.TestHandler):
            def handle(self, record):
                if record.extra.get('flag') != 'testing':
                    return False
                return logbook.TestHandler.handle(self, record)

        class MyLogger(logbook.Logger):
            def process_record(self, record):
                logbook.Logger.process_record(self, record)
                record.extra['flag'] = 'testing'
        log = MyLogger()
        handler = MyTestHandler()
        with capturing_stderr_context() as captured:
            with self.thread_activation_strategy(handler):
                log.warn('From my logger')
                self.log.warn('From another logger')
            self.assert_(handler.has_warning('From my logger'))
            self.assertIn('From another logger', captured.getvalue())

    def test_custom_handling_tester(self):
        flag = True

        class MyTestHandler(logbook.TestHandler):
            def should_handle(self, record):
                return flag
        null_handler = logbook.NullHandler()
        with self.thread_activation_strategy(null_handler):
            test_handler = MyTestHandler()
            with self.thread_activation_strategy(test_handler):
                self.log.warn('1')
                flag = False
                self.log.warn('2')
                self.assert_(test_handler.has_warning('1'))
                self.assert_(not test_handler.has_warning('2'))

    def test_null_handler(self):
        with capturing_stderr_context() as captured:
            with self.thread_activation_strategy(logbook.NullHandler()) as null_handler:
                with self.thread_activation_strategy(logbook.TestHandler(level='ERROR')) as handler:
                    self.log.error('An error')
                    self.log.warn('A warning')
            self.assertEqual(captured.getvalue(), '')
            self.assertFalse(handler.has_warning('A warning'))
            self.assert_(handler.has_error('An error'))

    def test_test_handler_cache(self):
        with self.thread_activation_strategy(logbook.TestHandler()) as handler:
            self.log.warn('First line')
            self.assertEqual(len(handler.formatted_records),1)
            cache = handler.formatted_records # store cache, to make sure it is identifiable
            self.assertEqual(len(handler.formatted_records),1)
            self.assert_(cache is handler.formatted_records) # Make sure cache is not invalidated without changes to record
            self.log.warn('Second line invalidates cache')
        self.assertEqual(len(handler.formatted_records),2)
        self.assertFalse(cache is handler.formatted_records) # Make sure cache is invalidated when records change

    def test_blackhole_setting(self):
        null_handler = logbook.NullHandler()
        heavy_init = logbook.LogRecord.heavy_init
        with self.thread_activation_strategy(null_handler):
            def new_heavy_init(self):
                raise RuntimeError('should not be triggered')
            logbook.LogRecord.heavy_init = new_heavy_init
            try:
                with self.thread_activation_strategy(null_handler):
                    logbook.warn('Awesome')
            finally:
                logbook.LogRecord.heavy_init = heavy_init

        null_handler.bubble = True
        with capturing_stderr_context() as captured:
            logbook.warning('Not a blockhole')
            self.assertNotEqual(captured.getvalue(), '')

    def test_calling_frame(self):
        handler = logbook.TestHandler()
        with self.thread_activation_strategy(handler):
            logbook.warn('test')
        self.assertEqual(handler.records[0].calling_frame, sys._getframe())

    def test_nested_setups(self):
        with capturing_stderr_context() as captured:
            logger = logbook.Logger('App')
            test_handler = logbook.TestHandler(level='WARNING')
            mail_handler = make_fake_mail_handler(bubble=True)

            handlers = logbook.NestedSetup([
                logbook.NullHandler(),
                test_handler,
                mail_handler
            ])

            with self.thread_activation_strategy(handlers):
                logger.warn('This is a warning')
                logger.error('This is also a mail')
                try:
                    1 / 0
                except Exception:
                    logger.exception()
            logger.warn('And here we go straight back to stderr')

            self.assert_(test_handler.has_warning('This is a warning'))
            self.assert_(test_handler.has_error('This is also a mail'))
            self.assertEqual(len(mail_handler.mails), 2)
            self.assertIn('This is also a mail', mail_handler.mails[0][2])
            self.assertIn('1 / 0',mail_handler.mails[1][2])
            self.assertIn('And here we go straight back to stderr',
                         captured.getvalue())

            with self.thread_activation_strategy(handlers):
                logger.warn('threadbound warning')

            handlers.push_application()
            try:
                logger.warn('applicationbound warning')
            finally:
                handlers.pop_application()

    def test_dispatcher(self):
        logger = logbook.Logger('App')
        with self.thread_activation_strategy(logbook.TestHandler()) as test_handler:
            logger.warn('Logbook is too awesome for stdlib')
            self.assertEqual(test_handler.records[0].dispatcher, logger)

    def test_filtering(self):
        logger1 = logbook.Logger('Logger1')
        logger2 = logbook.Logger('Logger2')
        handler = logbook.TestHandler()
        outer_handler = logbook.TestHandler()

        def only_1(record, handler):
            return record.dispatcher is logger1
        handler.filter = only_1

        with self.thread_activation_strategy(outer_handler):
            with self.thread_activation_strategy(handler):
                logger1.warn('foo')
                logger2.warn('bar')

        self.assert_(handler.has_warning('foo', channel='Logger1'))
        self.assertFalse(handler.has_warning('bar', channel='Logger2'))
        self.assertFalse(outer_handler.has_warning('foo', channel='Logger1'))
        self.assert_(outer_handler.has_warning('bar', channel='Logger2'))

    def test_different_context_pushing(self):
        h1 = logbook.TestHandler(level=logbook.DEBUG)
        h2 = logbook.TestHandler(level=logbook.INFO)
        h3 = logbook.TestHandler(level=logbook.WARNING)
        logger = logbook.Logger('Testing')

        with self.thread_activation_strategy(h1):
            with self.thread_activation_strategy(h2):
                with self.thread_activation_strategy(h3):
                    logger.warn('Wuuu')
                    logger.info('still awesome')
                    logger.debug('puzzled')

        self.assert_(h1.has_debug('puzzled'))
        self.assert_(h2.has_info('still awesome'))
        self.assert_(h3.has_warning('Wuuu'))
        for handler in h1, h2, h3:
            self.assertEquals(len(handler.records), 1)

    def test_global_functions(self):
        with self.thread_activation_strategy(logbook.TestHandler()) as handler:
            logbook.debug('a debug message')
            logbook.info('an info message')
            logbook.warn('warning part 1')
            logbook.warning('warning part 2')
            logbook.notice('notice')
            logbook.error('an error')
            logbook.critical('pretty critical')
            logbook.log(logbook.CRITICAL, 'critical too')

        self.assert_(handler.has_debug('a debug message'))
        self.assert_(handler.has_info('an info message'))
        self.assert_(handler.has_warning('warning part 1'))
        self.assert_(handler.has_warning('warning part 2'))
        self.assert_(handler.has_notice('notice'))
        self.assert_(handler.has_error('an error'))
        self.assert_(handler.has_critical('pretty critical'))
        self.assert_(handler.has_critical('critical too'))
        self.assertEqual(handler.records[0].channel, 'Generic')
        self.assertIsNone(handler.records[0].dispatcher)

    def test_fingerscrossed(self):
        handler = logbook.FingersCrossedHandler(logbook.default_handler,
                                                logbook.WARNING)

        # if no warning occurs, the infos are not logged
        with self.thread_activation_strategy(handler):
            with capturing_stderr_context() as captured:
                self.log.info('some info')
            self.assertEqual(captured.getvalue(), '')
            self.assert_(not handler.triggered)

        # but if it does, all log messages are output
        with self.thread_activation_strategy(handler):
            with capturing_stderr_context() as captured:
                self.log.info('some info')
                self.log.warning('something happened')
                self.log.info('something else happened')
            logs = captured.getvalue()
            self.assert_('some info' in logs)
            self.assert_('something happened' in logs)
            self.assert_('something else happened' in logs)
            self.assert_(handler.triggered)

    def test_fingerscrossed_factory(self):
        handlers = []

        def handler_factory(record, fch):
            handler = logbook.TestHandler()
            handlers.append(handler)
            return handler

        def make_fch():
            return logbook.FingersCrossedHandler(handler_factory,
                                                 logbook.WARNING)

        fch = make_fch()
        with self.thread_activation_strategy(fch):
            self.log.info('some info')
            self.assertEqual(len(handlers), 0)
            self.log.warning('a warning')
            self.assertEqual(len(handlers), 1)
            self.log.error('an error')
            self.assertEqual(len(handlers), 1)
            self.assert_(handlers[0].has_infos)
            self.assert_(handlers[0].has_warnings)
            self.assert_(handlers[0].has_errors)
            self.assert_(not handlers[0].has_notices)
            self.assert_(not handlers[0].has_criticals)
            self.assert_(not handlers[0].has_debugs)

        fch = make_fch()
        with self.thread_activation_strategy(fch):
            self.log.info('some info')
            self.log.warning('a warning')
            self.assertEqual(len(handlers), 2)

    def test_fingerscrossed_buffer_size(self):
        logger = logbook.Logger('Test')
        test_handler = logbook.TestHandler()
        handler = logbook.FingersCrossedHandler(test_handler, buffer_size=3)

        with self.thread_activation_strategy(handler):
            logger.info('Never gonna give you up')
            logger.warn('Aha!')
            logger.warn('Moar!')
            logger.error('Pure hate!')

        self.assertEqual(test_handler.formatted_records, [
            '[WARNING] Test: Aha!',
            '[WARNING] Test: Moar!',
            '[ERROR] Test: Pure hate!'
        ])


class HandlerTestCase_Regular(_HandlerTestCase):
    def setUp(self):
        super(HandlerTestCase_Regular, self).setUp()
        self.thread_activation_strategy = activate_via_push_pop

class HandlerTestCase_Contextmgr(_HandlerTestCase):
    def setUp(self):
        super(HandlerTestCase_Contextmgr, self).setUp()
        self.thread_activation_strategy = activate_via_with_statement

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
        self.assertEqual(self.log.group, group)
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
        group.remove_logger(self.log)
        self.assertEqual(self.log.group, None)

class LevelLookupTest(LogbookTestCase):
    def test_level_lookup_failures(self):
        with self.assertRaises(LookupError):
            logbook.get_level_name(37)
        with self.assertRaises(LookupError):
            logbook.lookup_level('FOO')

class FlagsTestCase(LogbookTestCase):
    def test_error_flag(self):
        with capturing_stderr_context() as captured:
            with logbook.Flags(errors='print'):
                with logbook.Flags(errors='silent'):
                    self.log.warn('Foo {42}', 'aha')
            self.assertEqual(captured.getvalue(), '')

            with logbook.Flags(errors='silent'):
                with logbook.Flags(errors='print'):
                    self.log.warn('Foo {42}', 'aha')
            self.assertNotEqual(captured.getvalue(), '')

            with self.assertRaises(Exception) as caught:
                with logbook.Flags(errors='raise'):
                    self.log.warn('Foo {42}', 'aha')
            self.assertIn('Could not format message with provided '
                          'arguments', str(caught.exception))

    def test_disable_introspection(self):
        with logbook.Flags(introspection=False):
            with logbook.TestHandler() as h:
                self.log.warn('Testing')
                self.assertIsNone(h.records[0].frame)
                self.assertIsNone(h.records[0].calling_frame)
                self.assertIsNone(h.records[0].module)

class LoggerGroupTestCase(LogbookTestCase):
    def test_groups(self):
        def inject_extra(record):
            record.extra['foo'] = 'bar'
        group = logbook.LoggerGroup(processor=inject_extra)
        group.level = logbook.ERROR
        group.add_logger(self.log)
        with logbook.TestHandler() as handler:
            self.log.warn('A warning')
            self.log.error('An error')
        self.assertFalse(handler.has_warning('A warning'))
        self.assertTrue(handler.has_error('An error'))
        self.assertEqual(handler.records[0].extra['foo'], 'bar')

class DefaultConfigurationTestCase(LogbookTestCase):

    def test_default_handlers(self):
        with capturing_stderr_context() as stream:
            self.log.warn('Aha!')
            captured = stream.getvalue()
        self.assertIn('WARNING: testlogger: Aha!', captured)

class LoggingCompatTestCase(LogbookTestCase):

    def test_basic_compat(self):
        from logging import getLogger
        from logbook.compat import redirected_logging

        name = 'test_logbook-%d' % randrange(1 << 32)
        logger = getLogger(name)
        with capturing_stderr_context() as captured:
            redirector = redirected_logging()
            redirector.start()
            try:
                logger.debug('This is from the old system')
                logger.info('This is from the old system')
                logger.warn('This is from the old system')
                logger.error('This is from the old system')
                logger.critical('This is from the old system')
            finally:
                redirector.end()
            self.assertIn(('WARNING: %s: This is from the old system' % name),
                          captured.getvalue())

    def test_redirect_logbook(self):
        import logging
        from logbook.compat import LoggingHandler
        out = StringIO()
        logger = logging.getLogger()
        old_handlers = logger.handlers[:]
        handler = logging.StreamHandler(out)
        handler.setFormatter(logging.Formatter(
            '%(name)s:%(levelname)s:%(message)s'))
        logger.handlers[:] = [handler]
        try:
            with logbook.compat.LoggingHandler() as logging_handler:
                self.log.warn("This goes to logging")
                pieces = out.getvalue().strip().split(':')
                self.assertEqual(pieces, [
                    'testlogger',
                    'WARNING',
                    'This goes to logging'
                ])
        finally:
            logger.handlers[:] = old_handlers

class WarningsCompatTestCase(LogbookTestCase):

    def test_warning_redirections(self):
        from logbook.compat import redirected_warnings
        with logbook.TestHandler() as handler:
            redirector = redirected_warnings()
            redirector.start()
            try:
                from warnings import warn
                warn(RuntimeWarning('Testing'))
            finally:
                redirector.end()

        self.assertEqual(len(handler.records), 1)
        self.assertEqual('[WARNING] RuntimeWarning: Testing',
                         handler.formatted_records[0])
        self.assertIn(__file_without_pyc__, handler.records[0].filename)

class MoreTestCase(LogbookTestCase):

    @contextmanager
    def _get_temporary_file_context(self):
        fn = tempfile.mktemp()
        try:
            yield fn
        finally:
            try:
                os.remove(fn)
            except OSError:
                pass

    @require_module('jinja2')
    def test_jinja_formatter(self):
        from logbook.more import JinjaFormatter
        fmter = JinjaFormatter('{{ record.channel }}/{{ record.level_name }}')
        handler = logbook.TestHandler()
        handler.formatter = fmter
        with handler:
            self.log.info('info')
        self.assertIn('testlogger/INFO', handler.formatted_records)

    @missing('jinja2')
    def test_missing_jinja2(self):
        from logbook.more import JinjaFormatter
        # check the RuntimeError is raised
        with self.assertRaises(RuntimeError):
            JinjaFormatter('dummy')

    def test_colorizing_support(self):
        from logbook.more import ColorizedStderrHandler

        class TestColorizingHandler(ColorizedStderrHandler):
            def should_colorize(self, record):
                return True
            stream = StringIO()
        with TestColorizingHandler(format_string='{record.message}') as handler:
            self.log.error('An error')
            self.log.warn('A warning')
            self.log.debug('A debug message')
            lines = handler.stream.getvalue().rstrip('\n').splitlines()
            self.assertEqual(lines, [
                '\x1b[31;01mAn error',
                '\x1b[39;49;00m\x1b[33;01mA warning',
                '\x1b[39;49;00m\x1b[37mA debug message',
                '\x1b[39;49;00m'
            ])

    def test_tagged(self):
        from logbook.more import TaggingLogger, TaggingHandler
        stream = StringIO()
        second_handler = logbook.StreamHandler(stream)

        logger = TaggingLogger('name', ['cmd'])
        handler = TaggingHandler(dict(
            info=logbook.default_handler,
            cmd=second_handler,
            both=[logbook.default_handler, second_handler],
        ))
        handler.bubble = False

        with handler:
            with capturing_stderr_context() as captured:
                logger.log('info', 'info message')
                logger.log('both', 'all message')
                logger.cmd('cmd message')

        stderr = captured.getvalue()

        self.assertIn('info message', stderr)
        self.assertIn('all message', stderr)
        self.assertNotIn('cmd message', stderr)

        stringio = stream.getvalue()

        self.assertNotIn('info message', stringio)
        self.assertIn('all message', stringio)
        self.assertIn('cmd message', stringio)

    def test_external_application_handler(self):
        from logbook.more import ExternalApplicationHandler as Handler
        with self._get_temporary_file_context() as fn:
            handler = Handler([sys.executable, '-c', r'''if 1:
                f = open(%(tempfile)s, 'w')
                try:
                    f.write('{record.message}\n')
                finally:
                    f.close()
            ''' % {'tempfile': repr(fn)}])
            with handler:
                self.log.error('this is a really bad idea')
            with open(fn, 'r') as rf:
                contents = rf.read().strip()
            self.assertEqual(contents, 'this is a really bad idea')

    def test_external_application_handler_stdin(self):
        from logbook.more import ExternalApplicationHandler as Handler
        with self._get_temporary_file_context() as fn:
            handler = Handler([sys.executable, '-c', r'''if 1:
                import sys
                f = open(%(tempfile)s, 'w')
                try:
                    f.write(sys.stdin.read())
                finally:
                    f.close()
            ''' % {'tempfile': repr(fn)}], '{record.message}\n')
            with handler:
                self.log.error('this is a really bad idea')
            with open(fn, 'r') as rf:
                contents = rf.read().strip()
            self.assertEqual(contents, 'this is a really bad idea')

    def test_exception_handler(self):
        from logbook.more import ExceptionHandler

        with ExceptionHandler(ValueError) as exception_handler:
            with self.assertRaises(ValueError) as caught:
                self.log.info('here i am')
        self.assertIn('INFO: testlogger: here i am', caught.exception.args[0])

    def test_exception_handler_specific_level(self):
        from logbook.more import ExceptionHandler
        with logbook.TestHandler() as test_handler:
            with self.assertRaises(ValueError) as caught:
                with ExceptionHandler(ValueError, level='WARNING') as exception_handler:
                    self.log.info('this is irrelevant')
                    self.log.warn('here i am')
            self.assertIn('WARNING: testlogger: here i am', caught.exception.args[0])
        self.assertIn('this is irrelevant', test_handler.records[0].message)

class QueuesTestCase(LogbookTestCase):
    def _get_zeromq(self):
        from logbook.queues import ZeroMQHandler, ZeroMQSubscriber

        # Get an unused port
        tempsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tempsock.bind(('localhost', 0))
        host, unused_port = tempsock.getsockname()
        tempsock.close()

        # Retrieve the ZeroMQ handler and subscriber
        uri = 'tcp://%s:%d' % (host, unused_port)
        handler = ZeroMQHandler(uri)
        subscriber = ZeroMQSubscriber(uri)
        # Enough time to start
        time.sleep(0.1)
        return handler, subscriber

    @require_module('zmq')
    def test_zeromq_handler(self):
        tests = [
            u'Logging something',
            u'Something with umlauts äöü',
            u'Something else for good measure',
        ]
        handler, subscriber = self._get_zeromq()
        for test in tests:
            with handler:
                self.log.warn(test)
                record = subscriber.recv()
                self.assertEqual(record.message, test)
                self.assertEqual(record.channel, self.log.name)

    @require_module('zmq')
    def test_zeromq_background_thread(self):
        handler, subscriber = self._get_zeromq()
        test_handler = logbook.TestHandler()
        controller = subscriber.dispatch_in_background(test_handler)

        with handler:
            self.log.warn('This is a warning')
            self.log.error('This is an error')

        # stop the controller.  This will also stop the loop and join the
        # background process.  Before that we give it a fraction of a second
        # to get all results
        time.sleep(0.1)
        controller.stop()

        self.assertTrue(test_handler.has_warning('This is a warning'))
        self.assertTrue(test_handler.has_error('This is an error'))

    @missing('zmq')
    def test_missing_zeromq(self):
        from logbook.queues import ZeroMQHandler, ZeroMQSubscriber
        with self.assertRaises(RuntimeError):
            ZeroMQHandler('tcp://127.0.0.1:42000')
        with self.assertRaises(RuntimeError):
            ZeroMQSubscriber('tcp://127.0.0.1:42000')

    @require_module('multiprocessing')
    def test_multi_processing_handler(self):
        from multiprocessing import Process, Queue
        from logbook.queues import MultiProcessingHandler, \
             MultiProcessingSubscriber
        queue = Queue(-1)
        test_handler = logbook.TestHandler()
        subscriber = MultiProcessingSubscriber(queue)

        def send_back():
            handler = MultiProcessingHandler(queue)
            handler.push_thread()
            try:
                logbook.warn('Hello World')
            finally:
                handler.pop_thread()

        p = Process(target=send_back)
        p.start()
        p.join()

        with test_handler:
            subscriber.dispatch_once()
            self.assert_(test_handler.has_warning('Hello World'))

    def test_threaded_wrapper_handler(self):
        from logbook.queues import ThreadedWrapperHandler
        test_handler = logbook.TestHandler()
        with ThreadedWrapperHandler(test_handler) as handler:
            self.log.warn('Just testing')
            self.log.error('More testing')

        # give it some time to sync up
        handler.close()

        self.assertTrue(not handler.controller.running)
        self.assertTrue(test_handler.has_warning('Just testing'))
        self.assertTrue(test_handler.has_error('More testing'))

    @require_module('execnet')
    def test_execnet_handler(self):
        def run_on_remote(channel):
            import logbook
            from logbook.queues import ExecnetChannelHandler
            handler = ExecnetChannelHandler(channel)
            log = logbook.Logger("Execnet")
            handler.push_application()
            log.info('Execnet works')

        import execnet
        gw = execnet.makegateway()
        channel = gw.remote_exec(run_on_remote)
        from logbook.queues import ExecnetChannelSubscriber
        subscriber = ExecnetChannelSubscriber(channel)
        record = subscriber.recv()
        self.assertEqual(record.msg, 'Execnet works')
        gw.exit()

    @require_module('multiprocessing')
    def test_subscriber_group(self):
        from multiprocessing import Process, Queue
        from logbook.queues import MultiProcessingHandler, \
                                   MultiProcessingSubscriber, SubscriberGroup
        a_queue = Queue(-1)
        b_queue = Queue(-1)
        test_handler = logbook.TestHandler()
        subscriber = SubscriberGroup([
            MultiProcessingSubscriber(a_queue),
            MultiProcessingSubscriber(b_queue)
        ])

        def make_send_back(message, queue):
            def send_back():
                with MultiProcessingHandler(queue):
                    logbook.warn(message)
            return send_back

        for _ in range(10):
            p1 = Process(target=make_send_back('foo', a_queue))
            p2 = Process(target=make_send_back('bar', b_queue))
            p1.start()
            p2.start()
            p1.join()
            p2.join()
            messages = [subscriber.recv().message for i in (1, 2)]
            self.assertEqual(sorted(messages), ['bar', 'foo'])

    @require_module('redis')
    def test_redis_handler(self):
        import redis
        from logbook.queues import RedisHandler

        KEY = 'redis'
        FIELDS = ['message', 'host']
        r = redis.Redis(decode_responses=True)
        redis_handler = RedisHandler(level=logbook.INFO, bubble=True)
        #We don't want output for the tests, so we can wrap everything in a NullHandler
        null_handler = logbook.NullHandler()

        #Check default values
        with null_handler.applicationbound():
            with redis_handler:
                logbook.info(LETTERS)

        key, message = r.blpop(KEY)
        #Are all the fields in the record?
        [self.assertTrue(message.find(field)) for field in FIELDS]
        self.assertEqual(key, KEY)
        self.assertTrue(message.find(LETTERS))

        #Change the key of the handler and check on redis
        KEY = 'test_another_key'
        redis_handler.key = KEY

        with null_handler.applicationbound():
            with redis_handler:
                logbook.info(LETTERS)

        key, message = r.blpop(KEY)
        self.assertEqual(key, KEY)

        #Check that extra fields are added if specified when creating the handler
        FIELDS.append('type')
        extra_fields = {'type': 'test'}
        del(redis_handler)
        redis_handler = RedisHandler(key=KEY, level=logbook.INFO,
                                     extra_fields=extra_fields, bubble=True)

        with null_handler.applicationbound():
            with redis_handler:
                logbook.info(LETTERS)

        key, message = r.blpop(KEY)
        [self.assertTrue(message.find(field)) for field in FIELDS]
        self.assertTrue(message.find('test'))

        #And finally, check that fields are correctly added if appended to the
        #log message
        FIELDS.append('more_info')
        with null_handler.applicationbound():
            with redis_handler:
                logbook.info(LETTERS, more_info='This works')

        key, message = r.blpop(KEY)
        [self.assertTrue(message.find(field)) for field in FIELDS]
        self.assertTrue(message.find('This works'))


class TicketingTestCase(LogbookTestCase):

    @require_module('sqlalchemy')
    def test_basic_ticketing(self):
        from logbook.ticketing import TicketingHandler
        with TicketingHandler('sqlite:///') as handler:
            for x in xrange(5):
                self.log.warn('A warning')
                self.log.info('An error')
                if x < 2:
                    try:
                        1 / 0
                    except Exception:
                        self.log.exception()

        self.assertEqual(handler.db.count_tickets(), 3)
        tickets = handler.db.get_tickets()
        self.assertEqual(len(tickets), 3)
        self.assertEqual(tickets[0].level, logbook.INFO)
        self.assertEqual(tickets[1].level, logbook.WARNING)
        self.assertEqual(tickets[2].level, logbook.ERROR)
        self.assertEqual(tickets[0].occurrence_count, 5)
        self.assertEqual(tickets[1].occurrence_count, 5)
        self.assertEqual(tickets[2].occurrence_count, 2)
        self.assertEqual(tickets[0].last_occurrence.level, logbook.INFO)

        tickets[0].solve()
        self.assert_(tickets[0].solved)
        tickets[0].delete()

        ticket = handler.db.get_ticket(tickets[1].ticket_id)
        self.assertEqual(ticket, tickets[1])

        occurrences = handler.db.get_occurrences(tickets[2].ticket_id,
                                                 order_by='time')
        self.assertEqual(len(occurrences), 2)
        record = occurrences[0]
        self.assertIn(__file_without_pyc__, record.filename)
        # avoid 2to3 destroying our assertion
        self.assertEqual(getattr(record, 'func_name'), 'test_basic_ticketing')
        self.assertEqual(record.level, logbook.ERROR)
        self.assertEqual(record.thread, get_ident())
        self.assertEqual(record.process, os.getpid())
        self.assertEqual(record.channel, 'testlogger')
        self.assertIn('1 / 0', record.formatted_exception)

class HelperTestCase(LogbookTestCase):

    def test_jsonhelper(self):
        from logbook.helpers import to_safe_json

        class Bogus(object):
            def __str__(self):
                return 'bogus'

        rv = to_safe_json([
            None,
            'foo',
            u'jäger',
            1,
            datetime(2000, 1, 1),
            {'jäger1': 1, u'jäger2': 2, Bogus(): 3, 'invalid': object()},
            object()  # invalid
        ])
        self.assertEqual(
            rv, [None, u'foo', u'jäger', 1, '2000-01-01T00:00:00Z',
                 {u('jäger1'): 1, u'jäger2': 2, u'bogus': 3,
                  u'invalid': None}, None])

    def test_datehelpers(self):
        from logbook.helpers import format_iso8601, parse_iso8601
        now = datetime.now()
        rv = format_iso8601()
        self.assertEqual(rv[:4], str(now.year))

        self.assertRaises(ValueError, parse_iso8601, 'foo')
        v = parse_iso8601('2000-01-01T00:00:00.12Z')
        self.assertEqual(v.microsecond, 120000)
        v = parse_iso8601('2000-01-01T12:00:00+01:00')
        self.assertEqual(v.hour, 11)
        v = parse_iso8601('2000-01-01T12:00:00-01:00')
        self.assertEqual(v.hour, 13)

class UnicodeTestCase(LogbookTestCase):
    # in Py3 we can just assume a more uniform unicode environment
    @require_py3
    def test_default_format_unicode(self):
        with capturing_stderr_context() as stream:
            self.log.warn('\u2603')
        self.assertIn('WARNING: testlogger: \u2603', stream.getvalue())

    @require_py3
    def test_default_format_encoded(self):
        with capturing_stderr_context() as stream:
            # it's a string but it's in the right encoding so don't barf
            self.log.warn('\u2603')
        self.assertIn('WARNING: testlogger: \u2603', stream.getvalue())

    @require_py3
    def test_default_format_bad_encoding(self):
        with capturing_stderr_context() as stream:
            # it's a string, is wrong, but just dump it in the logger,
            # don't try to decode/encode it
            self.log.warn('Русский'.encode('koi8-r'))
        self.assertIn("WARNING: testlogger: b'\\xf2\\xd5\\xd3\\xd3\\xcb\\xc9\\xca'", stream.getvalue())

    @require_py3
    def test_custom_unicode_format_unicode(self):
        format_string = ('[{record.level_name}] '
                         '{record.channel}: {record.message}')
        with capturing_stderr_context() as stream:
            with logbook.StderrHandler(format_string=format_string):
                self.log.warn("\u2603")
        self.assertIn('[WARNING] testlogger: \u2603', stream.getvalue())

    @require_py3
    def test_custom_string_format_unicode(self):
        format_string = ('[{record.level_name}] '
            '{record.channel}: {record.message}')
        with capturing_stderr_context() as stream:
            with logbook.StderrHandler(format_string=format_string):
                self.log.warn('\u2603')
        self.assertIn('[WARNING] testlogger: \u2603', stream.getvalue())

    @require_py3
    def test_unicode_message_encoded_params(self):
        with capturing_stderr_context() as stream:
            self.log.warn("\u2603 {0}", "\u2603".encode('utf8'))
        self.assertIn("WARNING: testlogger: \u2603 b'\\xe2\\x98\\x83'", stream.getvalue())

    @require_py3
    def test_encoded_message_unicode_params(self):
        with capturing_stderr_context() as stream:
            self.log.warn('\u2603 {0}'.encode('utf8'), '\u2603')
        self.assertIn('WARNING: testlogger: \u2603 \u2603', stream.getvalue())
