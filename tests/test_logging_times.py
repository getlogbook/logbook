from datetime import datetime, timedelta, timezone

import logbook


def test_default_time_is_aware_utc(activation_strategy, logger):
    """LogRecord.time is always a timezone-aware datetime in UTC."""
    handler = logbook.TestHandler()
    with activation_strategy(handler):
        logger.warning("This is a warning.")

    time = handler.records[0].time
    assert time.tzinfo is timezone.utc
    assert abs((datetime.now(timezone.utc) - time).total_seconds()) < 60


def test_default_format_string_includes_offset(activation_strategy, logger):
    handler = logbook.TestHandler(format_string=logbook.handlers.DEFAULT_FORMAT_STRING)
    with activation_strategy(handler):
        logger.warning("This is a warning.")

    assert "+0000]" in handler.formatted_records[0]


def _make_record(time=None):
    record = logbook.LogRecord("testlogger", logbook.WARNING, "message")
    record.heavy_init()
    if time is not None:
        record.time = time
    return record


def test_handler_tzinfo_converts_time():
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


def test_handler_tzinfo_treats_naive_time_as_local():
    """Naive times on hand-constructed records are interpreted as local
    time, like the standard library does.
    """
    handler = logbook.TestHandler(
        format_string="{record.time:%Y-%m-%d %H:%M %z}",
        tzinfo=timezone.utc,
    )
    naive = datetime(2020, 1, 1, 12, 0)
    record = _make_record(naive)
    expected = naive.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M %z")
    assert handler.format(record) == expected


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
    from logbook.more import ExceptionHandler, ExternalApplicationHandler
    from logbook.notifiers import NotificationBaseHandler, PushoverHandler

    zone = timezone(timedelta(hours=-7))
    for handler in [
        logbook.StreamHandler(None, tzinfo=zone),
        logbook.StderrHandler(tzinfo=zone),
        logbook.TestHandler(tzinfo=zone),
        ExceptionHandler(ValueError, tzinfo=zone),
        ExternalApplicationHandler(["true"], tzinfo=zone),
        NotificationBaseHandler(tzinfo=zone),
        PushoverHandler(tzinfo=zone),
    ]:
        assert handler.tzinfo is zone
    assert logbook.TestHandler().tzinfo is None


def test_handler_apply_tzinfo():
    record = _make_record(datetime(2020, 1, 1, 12, 0, tzinfo=timezone.utc))
    assert logbook.TestHandler().apply_tzinfo(record) is record

    handler = logbook.TestHandler(tzinfo=timezone(timedelta(hours=2)))
    converted = handler.apply_tzinfo(record)
    assert converted is not record
    assert converted.time == record.time
    assert converted.time.utcoffset() == timedelta(hours=2)
    assert converted.message == record.message


def test_handler_tzinfo_end_to_end(activation_strategy, logger):
    handler = logbook.TestHandler(
        format_string="{record.time:%z}",
        tzinfo=timezone(timedelta(hours=5, minutes=30)),
    )
    with activation_strategy(handler):
        logger.warning("this is a warning.")
    assert handler.formatted_records[0] == "+0530"


def test_aware_time_dict_roundtrip():
    """Record times survive to_dict/from_dict as timezone-aware UTC
    with the correct instant.
    """
    time = datetime(2020, 1, 1, 14, 30, 0, 5000, tzinfo=timezone(timedelta(hours=2)))
    record = _make_record(time)
    record.pull_information()
    imported = logbook.LogRecord.from_dict(record.to_dict(json_safe=True))
    assert imported.time == time
    assert imported.time.tzinfo is timezone.utc


def test_legacy_naive_dict_roundtrip():
    """Serialized records from Logbook 1.x carry naive UTC times with a
    Z suffix; they deserialize to aware UTC.
    """
    record = _make_record()
    record.pull_information()
    exported = record.to_dict(json_safe=True)
    exported["time"] = "2020-01-01T12:00:00.000005Z"
    imported = logbook.LogRecord.from_dict(exported)
    assert imported.time == datetime(2020, 1, 1, 12, 0, 0, 5, tzinfo=timezone.utc)
