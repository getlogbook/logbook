import gc
import sys

import logbook

from .utils import capturing_stderr_context


def test_exc_info_when_no_exceptions_exist(logger):
    with capturing_stderr_context() as captured:
        with logbook.StreamHandler(sys.stderr):
            logger.debug("message", exc_info=True)
    assert "Traceback" not in captured.getvalue()


def test_exc_info_false():
    with logbook.handlers.TestHandler() as handler:
        logbook.debug("message here", exc_info=False)
    [record] = handler.records
    assert not record.formatted_exception


def test_exc_info_exception_instance(logger):
    with logbook.handlers.TestHandler() as handler:
        try:
            raise ValueError("error here")
        except Exception as e:
            error = e
        logger.exception(exc_info=error)
    [record] = handler.records
    assert isinstance(record.exc_info, tuple)
    assert len(record.exc_info) == 3
    assert "Traceback" in record.formatted_exception


def test_extradict(active_handler, logger):
    logger.warning("Test warning")
    record = active_handler.records[0]
    record.extra["existing"] = "foo"
    assert record.extra["nonexisting"] == ""
    assert record.extra["existing"] == "foo"


def test_calling_frame(active_handler, logger):
    logger.warning("test")
    assert active_handler.records[0].calling_frame == sys._getframe()


def test_frame_correction(active_handler, logger):
    def inner():
        logger.warning("test", frame_correction=+1)

    inner()
    assert active_handler.records[0].calling_frame == sys._getframe()


def test_dispatcher(active_handler, logger):
    logger.warning("Logbook is too awesome for stdlib")
    assert active_handler.records[0].dispatcher == logger


class RecordKeeper(logbook.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


def test_dispatcher_is_weak():
    # Not TestHandler: its open records' frames keep the logger alive.
    logger = logbook.Logger("testlogger")
    with RecordKeeper() as handler:
        logger.warning("first")
        logger.warning("second")
    first, second = handler.records
    assert first.dispatcher is second.dispatcher is logger
    del logger
    gc.collect()
    assert first.dispatcher is None
    assert second.dispatcher is None
