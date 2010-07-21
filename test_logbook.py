import unittest
import logbook


class BasicAPITestCase(unittest.TestCase):

    def test_basic_logging(self):
        logger = logbook.Logger('Test Logger')
        handler = logbook.TestHandler()
        handler.formatter = logbook.SimpleFormatter()
        with handler.contextbound(bubble=False):
            logger.warning('This is a warning.  Nice hah?')

        logged = handler.get_contents()
        assert 'This is a warning' in logged


if __name__ == '__main__':
    unittest.main()
