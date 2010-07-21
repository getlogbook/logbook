import logbook

import os
import shutil
import unittest
import tempfile


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

        self.log = CustomLogger('awesome logger')
        handler = logbook.TestHandler()
        handler.formatter = logbook.SimpleFormatter(
            '[{record.level_name}] {record.logger_name}: '
            '{record.message} [{record.extra[ip]}]')

        with handler.contextbound(bubble=False):
            self.log.warn('"Music" playing')

        self.assertEqual(handler.formatted_records, [
            '[WARNING] awesome logger: "Music" playing [127.0.0.1]'
        ])


class HandlerTestCase(LogbookTestCase):

    def setUp(self):
        LogbookTestCase.setUp(self)
        self.dirname = tempfile.mkdtemp()
        self.filename = os.path.join(self.dirname, 'log.tmp')

    def tearDown(self):
        shutil.rmtree(self.dirname)
        LogbookTestCase.tearDown(self)

    def test_file_handler(self):
        formatter = logbook.SimpleFormatter(
            '{record.level_name}:{record.logger_name}:{record.message}')
        handler = logbook.FileHandler(self.filename)
        handler.formatter = formatter
        with handler.contextbound():
            self.log.warn('warning message')
        handler.close()
        with open(self.filename) as f:
            self.assertEqual(f.readline(),
                             'WARNING:testlogger:warning message\n')

    def test_lazy_file_handler(self):
        formatter = logbook.SimpleFormatter(
            '{record.level_name}:{record.logger_name}:{record.message}')
        handler = logbook.LazyFileHandler(self.filename)
        handler.formatter = formatter
        self.assertFalse(os.path.isfile(self.filename))
        with handler.contextbound():
            self.log.warn('warning message')
        handler.close()
        with open(self.filename) as f:
            self.assertEqual(f.readline(),
                             'WARNING:testlogger:warning message\n')


if __name__ == '__main__':
    unittest.main()
