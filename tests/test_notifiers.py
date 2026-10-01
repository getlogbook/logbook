import sys
from types import ModuleType

import pytest

import logbook
import logbook.notifiers
from logbook.notifiers import LibNotifyHandler, PushoverHandler


@pytest.fixture
def libnotify_shown(monkeypatch):
    shown = []
    provider = ModuleType("pynotify")
    provider.URGENCY_CRITICAL = 2
    provider.URGENCY_NORMAL = 1
    provider.URGENCY_LOW = 0
    provider.EXPIRES_NEVER = -1
    provider.EXPIRES_DEFAULT = 0
    provider.init = lambda application_name: None

    class Notification:
        def __init__(self, title, body):
            self.body = body

        def set_urgency(self, value):
            pass

        def set_timeout(self, value):
            pass

        def show(self):
            shown.append(self.body)

    provider.Notification = Notification
    gtk = ModuleType("gtk")
    gtk.gdk = ModuleType("gtk.gdk")
    monkeypatch.setitem(sys.modules, "pynotify", provider)
    monkeypatch.setitem(sys.modules, "gtk", gtk)
    monkeypatch.setitem(sys.modules, "gtk.gdk", gtk.gdk)
    return shown


@pytest.fixture
def pushover_requests(monkeypatch):
    requests = []

    class HTTPSConnection:
        def __init__(self, host):
            pass

        def request(self, method, path, body=None):
            requests.append(body)

        def close(self):
            pass

    monkeypatch.setattr(
        logbook.notifiers.http_client, "HTTPSConnection", HTTPSConnection
    )
    return requests


@pytest.mark.parametrize("introspection", [True, False])
def test_libnotify_record_limit(libnotify_shown, logger, introspection):
    with pytest.warns(DeprecationWarning, match="LibNotifyHandler is deprecated"):
        handler = LibNotifyHandler(record_limit=1)
    with logbook.Flags(errors="raise", introspection=introspection), handler:
        for _ in range(3):
            logger.warning("a repeated warning")
    assert len(libnotify_shown) == 1


@pytest.mark.parametrize("introspection", [True, False])
def test_pushover_record_limit(pushover_requests, logger, introspection):
    handler = PushoverHandler(apikey="token", userkey="user", record_limit=1)
    with logbook.Flags(errors="raise", introspection=introspection), handler:
        for _ in range(3):
            logger.warning("a repeated warning")
    assert len(pushover_requests) == 1
