from datetime import datetime


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
