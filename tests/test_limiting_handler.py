from datetime import datetime, timedelta

import pytest

import logbook


class RecordingMailHandler(logbook.MailHandler):
    def __init__(self, *, capacity=3, prune=0.5, record_limit=1):
        super().__init__(
            "from@example.test",
            ["to@example.test"],
            record_limit=record_limit,
            record_delta=timedelta(seconds=60),
        )
        self.max_record_cache = capacity
        self.record_cache_prune = prune
        self.deliveries = []

    def hash_record(self, record):
        # Known hashes distinguish age-based eviction from sorting by hash.
        return record.channel

    def generate_mail(self, record, suppressed=0):
        message = super().generate_mail(record, suppressed)
        message["X-Channel"] = record.channel
        return message

    def deliver(self, message, recipients):
        self.deliveries.append(message["X-Channel"])


def emit(handler, channel):
    with handler, logbook.Flags(errors="raise"):
        logbook.Logger(channel).error("Failure in {}", channel)


@pytest.fixture
def advance_clock(monkeypatch):
    now = datetime(2020, 1, 1)
    monkeypatch.setattr(logbook.handlers, "datetime_utcnow", lambda: now)

    def advance(seconds=1):
        nonlocal now
        now += timedelta(seconds=seconds)

    return advance


@pytest.mark.parametrize(
    ("capacity", "prune", "expected_hashes"),
    [
        (1, 0.333, {"new"}),
        (2, 0.333, {"old-1", "new"}),
        (3, 0.001, {"old-1", "old-2", "new"}),
        (4, 0.0, {"old-1", "old-2", "old-3", "new"}),
        (4, 0.5, {"old-2", "old-3", "new"}),
        (3, 1.0, {"new"}),
    ],
)
def test_mail_limiter_prunes_at_capacity(
    advance_clock, capacity, prune, expected_hashes
):
    handler = RecordingMailHandler(capacity=capacity, prune=prune)
    for index in range(capacity):
        emit(handler, f"old-{index}")
        advance_clock()
    assert len(handler._record_limits) == capacity

    emit(handler, "new")

    assert set(handler._record_limits) == expected_hashes
    assert len(handler._record_limits) <= capacity
    assert handler.deliveries == [
        *(f"old-{index}" for index in range(capacity)),
        "new",
    ]


def test_mail_limiter_evicts_oldest_interval_not_hash_or_last_access(advance_clock):
    handler = RecordingMailHandler()
    for channel in ("z", "a", "b"):
        emit(handler, channel)
        advance_clock()

    emit(handler, "z")
    advance_clock()
    emit(handler, "c")

    assert set(handler._record_limits) == {"a", "b", "c"}
    assert handler.deliveries == ["z", "a", "b", "c"]

    advance_clock()
    emit(handler, "a")
    assert set(handler._record_limits) == {"a", "b", "c"}
    assert handler.deliveries[-1] == "c"

    advance_clock()
    emit(handler, "z")
    assert set(handler._record_limits) == {"b", "c", "z"}
    assert handler.deliveries[-1] == "z"


def test_mail_limiter_preserves_counts_and_renews_retained_window(advance_clock):
    handler = RecordingMailHandler(capacity=2, record_limit=2)
    first_start = datetime(2020, 1, 1)
    a_start = first_start + timedelta(seconds=1)
    emit(handler, "z")
    advance_clock()
    emit(handler, "a")
    for _ in range(3):
        emit(handler, "z")

    assert handler.deliveries == ["z", "a", "z"]
    assert handler._record_limits == {"z": (first_start, 4), "a": (a_start, 1)}

    # Expiry is strict: a record exactly record_delta later is suppressed.
    advance_clock(59)
    emit(handler, "z")
    assert handler.deliveries == ["z", "a", "z"]
    assert handler._record_limits == {"z": (first_start, 5), "a": (a_start, 1)}

    advance_clock(0.001)
    emit(handler, "z")
    emit(handler, "z")
    emit(handler, "z")
    renewed_start = first_start + timedelta(seconds=60, microseconds=1000)
    assert handler.deliveries == ["z", "a", "z", "z", "z"]
    assert handler._record_limits == {"z": (renewed_start, 3), "a": (a_start, 1)}

    # Renewal moved z's interval start forward, so a is now the oldest entry.
    emit(handler, "b")
    assert handler._record_limits == {
        "z": (renewed_start, 3),
        "b": (renewed_start, 1),
    }
    assert handler.deliveries == ["z", "a", "z", "z", "z", "b"]
    emit(handler, "z")
    assert handler.deliveries == ["z", "a", "z", "z", "z", "b"]
    assert handler._record_limits == {
        "z": (renewed_start, 4),
        "b": (renewed_start, 1),
    }


def test_mail_limiter_respects_reduced_capacity(advance_clock):
    handler = RecordingMailHandler(capacity=4, prune=0.001)
    for channel in ("z", "a", "b", "c"):
        emit(handler, channel)
        advance_clock()

    handler.max_record_cache = 2
    emit(handler, "d")

    assert set(handler._record_limits) == {"c", "d"}
    assert len(handler._record_limits) == 2
    assert handler.deliveries[-1] == "d"


def test_mail_limiter_disabled_does_not_cache():
    handler = RecordingMailHandler(capacity=1, record_limit=None)
    for channel in ("same", "other", "same", "another"):
        emit(handler, channel)

    assert handler._record_limits == {}
    assert handler.deliveries == ["same", "other", "same", "another"]
