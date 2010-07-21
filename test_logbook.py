import unittest
import logbook


class BasicAPITestCase(unittest.TestCase):

    def test_basic_logging(self):
        logger = logbook.Logger('Test Logger')
        handler = logbook.TestHandler()
        with handler.contextbound(bubble=False):
            logger.warn('This is a warning.  Nice hah?')

        assert handler.has_warning('This is a warning.  Nice hah?')
        assert handler.formatted_records == [
            '[WARNING] Test Logger: This is a warning.  Nice hah?'
        ]


if __name__ == '__main__':
    unittest.main()
