import logbook

import os
import re
import sys
import shutil
import unittest
import tempfile
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
        with handler.contextbound():
            self.log.warn('warning message')
        handler.close()
        with open(self.filename) as f:
            self.assertEqual(f.readline(),
                             'WARNING:testlogger:warning message\n')

    def test_lazy_file_handler(self):
        handler = logbook.LazyFileHandler(self.filename, format_string=
            '{record.level_name}:{record.logger_name}:{record.message}')
        self.assertFalse(os.path.isfile(self.filename))
        with handler.contextbound():
            self.log.warn('warning message')
        handler.close()
        with open(self.filename) as f:
            self.assertEqual(f.readline(),
                             'WARNING:testlogger:warning message\n')

    def test_custom_formatter(self):
        def custom_format(record):
            return record.level_name + ':' + record.message
        with logbook.FileHandler(self.filename) as handler:
            handler.formatter = custom_format
            with handler.contextbound():
                self.log.warn('Custom formatters are awesome')
        with open(self.filename) as f:
            self.assertEqual(f.readline(),
                             'WARNING:Custom formatters are awesome\n')


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


if __name__ == '__main__':
    unittest.main()
