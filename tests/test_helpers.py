from datetime import datetime, timedelta, timezone

import pytest


def test_jsonhelper():
    from logbook.helpers import to_safe_json

    class Bogus:
        def __str__(self):
            return "bogus"

    rv = to_safe_json(
        [
            None,
            "foo",
            "jäger",
            1,
            datetime(2000, 1, 1),
            {"jäger1": 1, "jäger2": 2, Bogus(): 3, "invalid": object()},
            object(),  # invalid
        ]
    )

    assert rv == [
        None,
        "foo",
        "jäger",
        1,
        "2000-01-01T00:00:00Z",
        {"jäger1": 1, "jäger2": 2, "bogus": 3, "invalid": None},
        None,
    ]


def test_datehelpers():
    from logbook.helpers import format_iso8601, parse_iso8601

    now = datetime.now()
    rv = format_iso8601()
    assert rv[:4] == str(now.year)

    with pytest.raises(ValueError):
        parse_iso8601("foo")
    v = parse_iso8601("2000-01-01T00:00:00.12Z")
    assert v.microsecond == 120000
    assert v.tzinfo is timezone.utc
    v = parse_iso8601("2000-01-01T12:00:00+01:00")
    assert v.hour == 11
    v = parse_iso8601("2000-01-01T12:00:00-01:00")
    assert v.hour == 13


def test_format_iso8601_aware():
    from logbook.helpers import format_iso8601, parse_iso8601

    d = datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone(timedelta(hours=2)))
    rv = format_iso8601(d)
    assert rv == "2000-01-01T12:00:00+02:00"
    # the parsed value is normalized to UTC
    assert parse_iso8601(rv) == d
    assert parse_iso8601(rv).tzinfo is timezone.utc

    assert format_iso8601(datetime(2000, 1, 1, tzinfo=timezone.utc)) == (
        "2000-01-01T00:00:00+00:00"
    )


def test_format_iso8601_microseconds_roundtrip():
    from logbook.helpers import format_iso8601, parse_iso8601

    # regression test: microseconds used to be formatted without zero
    # padding, so 5000 microseconds roundtripped as 500000
    d = datetime(2000, 1, 1, 0, 0, 0, 5000)
    rv = format_iso8601(d)
    assert rv == "2000-01-01T00:00:00.005000Z"
    assert parse_iso8601(rv) == d.replace(tzinfo=timezone.utc)
