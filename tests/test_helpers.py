from datetime import datetime

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
    v = parse_iso8601("2000-01-01T12:00:00+01:00")
    assert v.hour == 11
    v = parse_iso8601("2000-01-01T12:00:00-01:00")
    assert v.hour == 13
