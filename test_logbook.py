import unittest
import logbook


class BasicAPITestCase(unittest.TestCase):

    def test_basic_logging(self):
        logger = logbook.Logger('Test Logger')
        handler = logbook.TestHandler()
        with handler.contextbound(bubble=False):
            logger.warn('This is a warning.  Nice hah?')

        assert 'Test Logger:This is a warning.  Nice hah?' in handler.records


if __name__ == '__main__':
    unittest.main()
