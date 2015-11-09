import sys
import logbook


class MyObject(object):
    def __init__(self, logger_func):
        self._logger_func = logger_func

    def __str__(self):
        self._logger_func("this debug message produced in __str__")
        return "<complex object>"


class FakeLock(object):
    def __init__(self):
        self._acquired = False
        self._deadlock_occurred = False

    def acquire(self):
        if self._acquired:
            self._deadlock_occurred = True
        self._acquired = True

    def release(self):
        self._acquired = False


def test_deadlock_in_emit():
    logbook_logger = logbook.Logger("logbook")
    obj = MyObject(logbook_logger.info)
    stream_handler = logbook.StreamHandler(stream=sys.stderr,
                                           level=logbook.DEBUG)
    stream_handler.lock = FakeLock()
    with stream_handler.applicationbound():
        logbook_logger.info("format this: {}", obj)
    assert not stream_handler.lock._deadlock_occurred
