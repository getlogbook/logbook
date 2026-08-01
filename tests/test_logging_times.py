from datetime import datetime, timedelta, timezone, tzinfo

import pytest

import logbook


def set_datetime_format(datetime_format):
    """logbook.set_datetime_format() is deprecated; these tests exercise
    its behavior until it is removed, so silence the warning.
    """
    with pytest.deprecated_call(match="set_datetime_format"):
        logbook.set_datetime_format(datetime_format)


def test_timedate_format(activation_strategy, logger):
    """
    tests the logbook.set_datetime_format() function
    """
    FORMAT_STRING = "{record.time:%H:%M:%S.%f} {record.message}"
    handler = logbook.TestHandler(format_string=FORMAT_STRING)
    with activation_strategy(handler):
        set_datetime_format("utc")
        try:
            logger.warning("This is a warning.")
            time_utc = handler.records[0].time
            set_datetime_format("local")
            logger.warning("This is a warning.")
            time_local = handler.records[1].time
        finally:
            # put back the default time factory
            set_datetime_format("utc")

    # get the expected difference between local and utc time
    t1 = datetime.now()
    t2 = datetime.now(timezone.utc).replace(tzinfo=None)

    tz_minutes_diff = (t1 - t2).total_seconds() / 60.0

    if abs(tz_minutes_diff) < 1:
        pytest.skip(
            "Cannot test utc/localtime differences "
            "if they vary by less than one minute..."
        )

    # get the difference between LogRecord local and utc times
    logbook_minutes_diff = (time_local - time_utc).total_seconds() / 60.0
    assert abs(logbook_minutes_diff) > 1, (
        "Localtime does not differ from UTC by more than 1 "  # noqa: UP031
        "minute (Local: %s, UTC: %s)" % (time_local, time_utc)
    )

    ratio = logbook_minutes_diff / tz_minutes_diff

    assert ratio > 0.99
    assert ratio < 1.01


def test_tz_aware(activation_strategy, logger):
    """
    tests logbook.set_datetime_format() with a time zone aware time factory
    """

    class utc(tzinfo):
        def tzname(self, dt):
            return "UTC"

        def utcoffset(self, dt):
            return timedelta(seconds=0)

        def dst(self, dt):
            return timedelta(seconds=0)

    utc = utc()

    def utc_tz():
        return datetime.now(tz=utc)

    FORMAT_STRING = "{record.time:%H:%M:%S.%f%z} {record.message}"
    handler = logbook.TestHandler(format_string=FORMAT_STRING)
    with activation_strategy(handler):
        set_datetime_format(utc_tz)
        try:
            logger.warning("this is a warning.")
            record = handler.records[0]
        finally:
            # put back the default time factory
            set_datetime_format("utc")

    assert record.time.tzinfo is not None


def test_invalid_time_factory():
    """
    tests logbook.set_datetime_format() with an invalid time factory callable
    """

    def invalid_factory():
        return False

    with pytest.raises(ValueError) as e:
        try:
            set_datetime_format(invalid_factory)
        finally:
            # put back the default time factory
            set_datetime_format("utc")

    assert "Invalid callable value" in str(e.value)


def test_set_datetime_format_is_deprecated():
    with pytest.deprecated_call(match="Logbook 2.0"):
        logbook.set_datetime_format("utc")


def _make_record(time=None):
    record = logbook.LogRecord("testlogger", logbook.WARNING, "message")
    record.heavy_init()
    if time is not None:
        record.time = time
    return record


def test_handler_tzinfo_converts_aware_time():
    handler = logbook.TestHandler(
        format_string="{record.time:%Y-%m-%d %H:%M %z}",
        tzinfo=timezone(timedelta(hours=2)),
    )
    record = _make_record(datetime(2020, 1, 1, 12, 0, tzinfo=timezone.utc))
    assert handler.format(record) == "2020-01-01 14:00 +0200"


def test_handler_tzinfo_local():
    handler = logbook.TestHandler(format_string="{record.time:%z}", tzinfo="local")
    time = datetime(2020, 1, 1, 12, 0, tzinfo=timezone.utc)
    record = _make_record(time)
    expected = time.astimezone(None).strftime("%z")
    assert handler.format(record) == expected


def test_handler_tzinfo_leaves_naive_time_unchanged():
    handler = logbook.TestHandler(
        format_string="{record.time:%H:%M%z}",
        tzinfo=timezone(timedelta(hours=2)),
    )
    record = _make_record(datetime(2020, 1, 1, 12, 0))
    assert handler.format(record) == "12:00"


def test_handler_tzinfo_does_not_mutate_record():
    handler = logbook.TestHandler(
        format_string="{record.time:%H:%M}",
        tzinfo=timezone(timedelta(hours=2)),
    )
    time = datetime(2020, 1, 1, 12, 0, tzinfo=timezone.utc)
    record = _make_record(time)
    handler.format(record)
    assert record.time == time
    assert record.time.tzinfo is timezone.utc


def test_handler_tzinfo_constructor():
    zone = timezone(timedelta(hours=-7))
    for handler in [
        logbook.StreamHandler(None, tzinfo=zone),
        logbook.StderrHandler(tzinfo=zone),
        logbook.TestHandler(tzinfo=zone),
    ]:
        assert handler.tzinfo is zone
    assert logbook.TestHandler().tzinfo is None


def test_handler_tzinfo_with_aware_factory(activation_strategy, logger):
    handler = logbook.TestHandler(
        format_string="{record.time:%z}",
        tzinfo=timezone(timedelta(hours=5, minutes=30)),
    )
    set_datetime_format(lambda: datetime.now(timezone.utc))
    try:
        with activation_strategy(handler):
            logger.warning("this is a warning.")
    finally:
        set_datetime_format("utc")
    assert handler.formatted_records[0] == "+0530"


def test_aware_time_dict_roundtrip():
    """Aware record times survive to_dict/from_dict with the correct
    instant; the parsed value is normalized to naive UTC in Logbook 1.x.
    """
    time = datetime(2020, 1, 1, 14, 30, 0, 5000, tzinfo=timezone(timedelta(hours=2)))
    record = _make_record(time)
    record.pull_information()
    imported = logbook.LogRecord.from_dict(record.to_dict(json_safe=True))
    assert imported.time == datetime(2020, 1, 1, 12, 30, 0, 5000)
