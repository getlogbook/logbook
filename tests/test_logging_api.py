import pickle
import sys
from datetime import datetime, timezone

import pytest

import logbook


def test_basic_logging(active_handler, logger):
    logger.warning("This is a warning.  Nice hah?")

    assert active_handler.has_warning("This is a warning.  Nice hah?")
    assert active_handler.formatted_records == [
        "[WARNING] testlogger: This is a warning.  Nice hah?"
    ]


def test_exception_catching(active_handler, logger):
    assert not active_handler.has_error()
    try:
        1 / 0  # noqa: B018
    except Exception:
        logger.exception()
    try:
        1 / 0  # noqa: B018
    except Exception:
        logger.exception("Awesome")
    assert active_handler.has_error("Uncaught exception occurred")
    assert active_handler.has_error("Awesome")
    assert active_handler.records[0].exc_info is not None
    assert "1 / 0" in active_handler.records[0].formatted_exception


def test_exception_catching_with_unicode():
    """See https://github.com/getlogbook/logbook/issues/104"""
    try:
        raise Exception("\u202a test \u202c")
    except Exception:
        r = logbook.LogRecord("channel", "DEBUG", "test", exc_info=sys.exc_info())
    r.exception_message  # noqa: B018


@pytest.mark.parametrize("as_tuple", [True, False])
def test_exc_info(as_tuple, logger, active_handler):
    try:
        1 / 0  # noqa: B018
    except Exception:
        exc_info = sys.exc_info()
        logger.info("Exception caught", exc_info=exc_info if as_tuple else True)
    assert active_handler.records[0].exc_info is not None
    assert active_handler.records[0].exc_info == exc_info


def test_to_dict(logger, active_handler):
    try:
        1 / 0  # noqa: B018
    except Exception:
        logger.exception()
        record = active_handler.records[0]

    exported = record.to_dict()
    record.close()
    imported = logbook.LogRecord.from_dict(exported)
    for key, value in record.__dict__.items():
        if key[0] == "_":
            continue
        assert value == getattr(imported, key)


def test_json_export_time_in_repeated_hour(record_time):
    record = logbook.LogRecord("test", logbook.INFO, "message")
    # 01:10 EST, the second time the clocks show 01:10 that day.
    dt = datetime(2026, 11, 1, 6, 10, 0, 123456, tzinfo=timezone.utc)
    record.time = record_time(dt)

    exported = record.to_dict(json_safe=True)
    assert exported["time"] == "2026-11-01T06:10:00.123456Z"
    imported = logbook.LogRecord.from_dict(exported)
    assert (imported.time, imported.time.fold) == (record.time, record.time.fold)


@pytest.mark.parametrize(
    "utc",
    [
        # 01:10 EDT, then 01:10 EST an hour later.
        datetime(2026, 11, 1, 5, 10, tzinfo=timezone.utc),
        datetime(2026, 11, 1, 6, 10, tzinfo=timezone.utc),
        # A float timestamp this late can't hold every microsecond.
        datetime(3000, 1, 1, 12, 0, 0, 895989, tzinfo=timezone.utc),
    ],
)
def test_local_record_time_round_trip(new_york, monkeypatch, utc):
    monkeypatch.setattr(logbook.base, "_datetime_mode", "local")
    local = logbook.base._record_time_from_utc(utc)
    assert local.tzinfo is None
    assert logbook.base._record_time_to_utc(local) == utc


@pytest.mark.parametrize("zone", ["fixed offset", "time zone"])
def test_aware_record_time_from_utc_across_dst(new_york, monkeypatch, zone):
    for name in ("_datetime_factory", "_datetime_mode", "_datetime_tzinfo"):
        monkeypatch.setattr(logbook.base, name, getattr(logbook.base, name))
    tz = None if zone == "fixed offset" else new_york
    # Set in summer, then read back a December record.
    clock = datetime(2026, 7, 1, 12, tzinfo=timezone.utc)
    logbook.set_datetime_format(lambda: clock.astimezone(tz))
    clock = datetime(2026, 12, 15, 17, tzinfo=timezone.utc)
    result = logbook.base._record_time_from_utc(clock)
    assert result.isoformat() == "2026-12-15T12:00:00-05:00"


def test_pickle(active_handler, logger):
    try:
        1 / 0  # noqa: B018
    except Exception:
        logger.exception()
        record = active_handler.records[0]
    record.pull_information()
    record.close()

    for p in range(pickle.HIGHEST_PROTOCOL):
        exported = pickle.dumps(record, p)
        imported = pickle.loads(exported)
        for key, value in record.__dict__.items():
            if key[0] == "_":
                continue
            imported_value = getattr(imported, key)
            if isinstance(value, ZeroDivisionError):
                # in Python 3.2, ZeroDivisionError(x) != ZeroDivisionError(x)
                assert type(value) is type(imported_value)
                assert value.args == imported_value.args
            else:
                assert value == imported_value
