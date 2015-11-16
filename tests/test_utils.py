from time import sleep
from logbook.utils import log_if_slow_context

_THRESHOLD = 0.1


def test_log_if_slow_context_reached(logger, test_handler):
    with test_handler.applicationbound():
        with log_if_slow_context('checking...', threshold=_THRESHOLD):
            sleep(2*_THRESHOLD)
        assert len(test_handler.records) == 1
        [record] = test_handler.records
        assert record.message == 'checking...'

def test_log_if_slow_context_did_not_reached(logger, test_handler):
    with test_handler.applicationbound():
        with log_if_slow_context('checking...', threshold=_THRESHOLD):
            sleep(_THRESHOLD/2)
        assert len(test_handler.records) == 0
