import functools
import logging
import logging.handlers
import sys
import warnings
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from io import StringIO
from itertools import count
from random import randrange

import pytest

import logbook
import logbook.compat

from .utils import capturing_stderr_context

__file_without_pyc__ = __file__
if __file_without_pyc__.endswith(".pyc"):
    __file_without_pyc__ = __file_without_pyc__[:-1]


@pytest.mark.parametrize("set_root_logger_level", [True, False])
def test_basic_compat(request, set_root_logger_level):
    import logging

    from logbook.compat import redirected_logging

    # mimic the default logging setting
    request.addfinalizer(functools.partial(logging.root.setLevel, logging.root.level))
    logging.root.setLevel(logging.WARNING)

    name = "test_logbook-%d" % randrange(1 << 32)  # noqa: UP031
    logger = logging.getLogger(name)

    with logbook.TestHandler(bubble=True) as handler:
        with capturing_stderr_context() as captured:
            with redirected_logging(set_root_logger_level):
                logger.debug("This is from the old system")
                logger.info("This is from the old system")
                logger.warning("This is from the old %s", "system")
                logger.error("This is from the old system")
                logger.critical("This is from the old system")
                logger.error(
                    "This is a %(what)s %(where)s", {"what": "mapping", "where": "test"}
                )
        assert (
            "WARNING: %s: This is from the old system" % name  # noqa: UP031
        ) in captured.getvalue()
        assert ("ERROR: %s: This is a mapping test" % name) in captured.getvalue()  # noqa: UP031
    if set_root_logger_level:
        assert handler.records[0].level == logbook.DEBUG
    else:
        assert handler.records[0].level == logbook.WARNING
        assert handler.records[0].msg == "This is from the old %s"


def test_redirect_logbook():
    import logging

    out = StringIO()
    logger = logging.getLogger()
    logbook_logger = logbook.Logger("testlogger")
    old_handlers = logger.handlers[:]
    handler = logging.StreamHandler(out)
    handler.setFormatter(logging.Formatter("%(name)s:%(levelname)s:%(message)s"))
    logger.handlers[:] = [handler]
    try:
        with logbook.compat.LoggingHandler():
            logbook_logger.warning("This goes to logging")
            pieces = out.getvalue().strip().split(":")
            assert pieces == ["testlogger", "WARNING", "This goes to logging"]
    finally:
        logger.handlers[:] = old_handlers


def test_logging_handler_time_in_repeated_hour(record_time):
    # 01:50 EDT, then 01:10 EST twenty minutes later.
    for hour, minute in [(5, 50), (6, 10)]:
        dt = datetime(2026, 11, 1, hour, minute, tzinfo=timezone.utc)
        created = logbook.compat.LoggingHandler().convert_time(record_time(dt))
        assert created == dt.timestamp()


test_warning_redirections_i = count()


def test_warning_redirections():
    from logbook.compat import redirected_warnings

    with logbook.TestHandler() as handler:
        with redirected_warnings():
            warnings.warn(  # noqa: B028
                RuntimeWarning(f"Testing {next(test_warning_redirections_i)}")
            )

    assert len(handler.formatted_records) == 1
    assert handler.formatted_records[0].startswith("[WARNING] RuntimeWarning: Testing")
    assert __file_without_pyc__ in handler.records[0].filename


@pytest.mark.parametrize(
    "time, created, msecs",
    [
        (datetime(2023, 11, 14, 22, 13, 20, 123456), 1700000000.123456, 123.0),
        (
            datetime(2023, 11, 14, 23, 13, 20, 1000, timezone(timedelta(hours=1))),
            1700000000.001,
            1.0,
        ),
        (datetime(1969, 12, 31, 23, 59, 59, 123456), -0.876544, 123.0),
    ],
)
def test_logging_handler_event_time(time, created, msecs):
    old_record = logbook.LogRecord("source", logbook.INFO, "event")
    old_record.time = time
    record = logbook.compat.LoggingHandler().convert_record(old_record)
    assert record.created == created
    assert record.msecs == msecs
    start = logging._startTime
    if sys.version_info >= (3, 13):
        start /= 1e9
    assert record.relativeCreated == pytest.approx((created - start) * 1000, abs=0.01)


@pytest.mark.parametrize(
    "created, msecs",
    [
        (1700000000.1239996, 123.0),
        (1700000000.9999998, 999.0),
        (Decimal("1700000000.125"), 125.0),
    ],
)
def test_logging_handler_converted_time_override(created, msecs):
    class EpochHandler(logbook.compat.LoggingHandler):
        def convert_time(self, dt):
            return created

    old_record = logbook.LogRecord("source", logbook.INFO, "event")
    record = EpochHandler().convert_record(old_record)
    assert record.created == created
    assert record.msecs == msecs


def test_redirect_keeps_event_time(record_time):
    # 01:10 EST, the second time the clocks show 01:10 that day.
    event = datetime(2026, 11, 1, 6, 10, 0, 123456, tzinfo=timezone.utc)
    source = logging.LogRecord(
        "source", logging.WARNING, __file__, 1, "event", (), None
    )
    source.created = event.timestamp()
    with logbook.TestHandler() as handler:
        logbook.compat.RedirectLoggingHandler().handle(source)
    [record] = handler.records
    assert repr(record.time) == repr(record_time(event))


def test_redirect_convert_time_override_sets_time():
    class Custom(logbook.compat.RedirectLoggingHandler):
        def convert_time(self, timestamp):
            return datetime(2003, 2, 1)

    source = logging.LogRecord(
        "source", logging.WARNING, __file__, 1, "event", (), None
    )
    with logbook.TestHandler() as handler:
        Custom().handle(source)
    [record] = handler.records
    assert record.time == datetime(2003, 2, 1)


@pytest.mark.parametrize("stacklevel", [1, 2])
def test_redirect_preserves_stdlib_caller(stacklevel):
    def helper():
        logging.getLogger("source").warning("event", stacklevel=stacklevel)

    def caller():
        helper()

    with logbook.TestHandler() as handler, logbook.compat.redirected_logging():
        caller()
    [record] = handler.records
    code = (helper if stacklevel == 1 else caller).__code__
    assert (record.func_name, record.lineno) == (
        code.co_name,
        code.co_firstlineno + 1,
    )


def test_redirect_buffered_records_keep_their_own_caller():
    logger = logging.Logger("buffered")
    redirect = logbook.compat.RedirectLoggingHandler()
    logger.addHandler(logging.handlers.MemoryHandler(2, target=redirect))

    def load():
        logger.warning("loading")

    def fail():
        logger.warning("failed")

    with logbook.TestHandler() as handler:
        load()
        fail()
    assert [(r.func_name, r.lineno) for r in handler.records] == [
        ("load", load.__code__.co_firstlineno + 1),
        ("fail", fail.__code__.co_firstlineno + 1),
    ]


def test_redirect_replayed_record_keeps_source_metadata():
    source = logging.LogRecord(
        "source",
        logging.WARNING,
        "/application/original.py",
        123,
        "event",
        (),
        None,
        func="original_caller",
    )
    source.thread, source.threadName = 12345, "origin-thread"
    source.process, source.processName = 54321, "origin-process"
    with logbook.TestHandler() as handler:
        logbook.compat.RedirectLoggingHandler().handle(source)
    [record] = handler.records
    assert (record.filename, record.lineno, record.func_name, record.module) == (
        "/application/original.py",
        123,
        "original_caller",
        "original",
    )
    assert (record.thread, record.thread_name, record.process, record.process_name) == (
        12345,
        "origin-thread",
        54321,
        "origin-process",
    )


def test_redirect_uses_frame_when_stdlib_caller_is_unknown(monkeypatch):
    monkeypatch.setattr(logging, "_srcfile", None)

    def app_function():
        logging.getLogger("source").warning("without caller lookup")

    with logbook.TestHandler() as handler, logbook.compat.redirected_logging():
        app_function()
    [record] = handler.records
    assert record.func_name == "app_function"


def test_redirect_find_caller_override_sets_location():
    class CustomHandler(logbook.compat.RedirectLoggingHandler):
        def find_caller(self, old_record):
            return frame

    frame = sys._getframe()
    source = logging.LogRecord(
        "source", logging.WARNING, "/application/source.py", 42, "event", (), None
    )
    record = CustomHandler().convert_record(source)
    assert record.func_name == "test_redirect_find_caller_override_sets_location"
