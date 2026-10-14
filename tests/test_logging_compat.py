import functools
import logging
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
