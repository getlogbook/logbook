import importlib.util
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import logbook

logbook.StderrHandler().push_application()


@pytest.fixture
def logger():
    return logbook.Logger("testlogger")


@pytest.fixture
def active_handler(request, test_handler, activation_strategy):
    s = activation_strategy(test_handler)
    s.activate()

    @request.addfinalizer
    def deactivate():
        s.deactivate()

    return test_handler


@pytest.fixture
def test_handler():
    return logbook.TestHandler()


class ActivationStrategy:
    def __init__(self, handler):
        super().__init__()
        self.handler = handler

    def activate(self):
        raise NotImplementedError()  # pragma: no cover

    def deactivate(self):
        raise NotImplementedError()  # pragma: no cover

    def __enter__(self):
        self.activate()
        return self.handler

    def __exit__(self, *_):
        self.deactivate()


class ContextEnteringStrategy(ActivationStrategy):
    def activate(self):
        self.handler.__enter__()

    def deactivate(self):
        self.handler.__exit__(None, None, None)


class PushingStrategy(ActivationStrategy):
    def activate(self):
        self.handler.push_context()

    def deactivate(self):
        self.handler.pop_context()


@pytest.fixture(params=[ContextEnteringStrategy, PushingStrategy])
def activation_strategy(request):
    return request.param


class CustomPathLike:
    def __init__(self, path):
        self.path = path

    def __fspath__(self):
        return self.path


@pytest.fixture(params=[Path, str, CustomPathLike])
def logfile(tmp_path, request):
    path = str(tmp_path / "logfile.log")
    return request.param(path)


@pytest.fixture
def new_york(monkeypatch):
    if not hasattr(time, "tzset"):
        pytest.skip("needs time.tzset()")
    monkeypatch.setenv("TZ", "America/New_York")
    time.tzset()
    yield ZoneInfo("America/New_York")
    monkeypatch.undo()
    time.tzset()


@pytest.fixture(params=["utc", "local", "aware"])
def record_time(request, new_york):
    """Selects each set_datetime_format() mode in New York, and returns a
    function that gives the record time for an aware datetime in that mode.
    """
    mode = request.param
    datetime_format = (lambda: datetime.now(new_york)) if mode == "aware" else mode
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        logbook.set_datetime_format(datetime_format)
    yield {
        "utc": lambda dt: dt.astimezone(timezone.utc).replace(tzinfo=None),
        "local": lambda dt: datetime.fromtimestamp(dt.timestamp()),
        "aware": lambda dt: dt.astimezone(new_york),
    }[mode]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        logbook.set_datetime_format("utc")


@pytest.fixture
def set_clock():
    """Fixes the time Logbook reads, keeping the current set_datetime_format() mode."""
    base = logbook.base
    saved = base._datetime_factory, base._datetime_mode, base._datetime_tzinfo

    def set_clock(when):
        now = base._record_time_from_utc(when)
        base._datetime_factory = lambda: now

    yield set_clock
    base._datetime_factory, base._datetime_mode, base._datetime_tzinfo = saved


@pytest.fixture
def default_handler(request):
    returned = logbook.StderrHandler()
    returned.push_application()
    request.addfinalizer(returned.pop_application)
    return returned


if importlib.util.find_spec("gevent") is not None:

    @pytest.fixture(
        scope="module", autouse=True, params=[False, True], ids=["nogevent", "gevent"]
    )
    def gevent(request):
        module_name = getattr(request.module, "__name__", "")
        if (
            not any(s in module_name for s in ("queues", "processors"))
            and request.param
        ):
            from logbook.concurrency import _disable_gevent, enable_gevent

            enable_gevent()

            @request.addfinalizer
            def fin():
                _disable_gevent()
