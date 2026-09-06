import os
import re
import socket
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timezone

import pytest

import logbook

UNIX_SOCKET = "/tmp/__unixsock_logbook.test"

DELIMITERS = {socket.AF_INET: "\n"}

TO_TEST = [
    (socket.AF_INET, socket.SOCK_DGRAM, ("127.0.0.1", 0)),
    (socket.AF_INET, socket.SOCK_STREAM, ("127.0.0.1", 0)),
]

UNIX_SOCKET_AVAILABLE = hasattr(socket, "AF_UNIX")

if UNIX_SOCKET_AVAILABLE:
    DELIMITERS[socket.AF_UNIX] = "\x00"
    TO_TEST.append((socket.AF_UNIX, socket.SOCK_DGRAM, UNIX_SOCKET))


@pytest.mark.usefixtures("unix_sock_path")
@pytest.mark.parametrize("sock_family,socktype,address", TO_TEST)
@pytest.mark.parametrize("app_name", [None, "Testing"])
def test_syslog_handler(
    logger, activation_strategy, sock_family, socktype, address, app_name
):
    delimiter = DELIMITERS[sock_family]
    with closing(socket.socket(sock_family, socktype)) as inc:
        inc.bind(address)

        if socktype == socket.SOCK_STREAM:
            inc.listen(1)

        inc.settimeout(1)

        if UNIX_SOCKET_AVAILABLE and sock_family == socket.AF_UNIX:
            expected = r"^<12>{}testlogger: Syslog is weird{}$".format(
                app_name + ":" if app_name else "", delimiter
            )
        else:
            expected = (
                r"^<12>1 \d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?Z %s %s %d - - %sSyslog is weird%s$"  # noqa: UP031
                % (
                    socket.gethostname(),
                    app_name if app_name else "testlogger",
                    os.getpid(),
                    "testlogger: " if app_name else "",
                    delimiter,
                )
            )

        handler = logbook.SyslogHandler(app_name, inc.getsockname(), socktype=socktype)

        with activation_strategy(handler):
            logger.warning("Syslog is weird")

        if socktype == socket.SOCK_STREAM:
            with closing(inc.accept()[0]) as inc2:
                rv = inc2.recv(1024)
        else:
            rv = inc.recvfrom(1024)[0]

        rv = rv.decode("utf-8")
        assert re.match(expected, rv), f"expected {expected}, got {rv}"


@pytest.fixture
def unix_sock_path():
    try:
        yield UNIX_SOCKET
    finally:
        if os.path.exists(UNIX_SOCKET):
            os.unlink(UNIX_SOCKET)


@pytest.fixture
def udp_server():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server:
        server.bind(("127.0.0.1", 0))
        server.settimeout(2)
        yield server


def receive(server):
    """Returns the timestamp, app-name and message of an RFC 5424 datagram."""
    fields = server.recv(1024).decode("utf-8").split(" ", 7)
    return fields[1], fields[3], fields[7]


def test_syslog_concurrent_channels(udp_server):
    entered = threading.Event()
    release = threading.Event()

    class BlockingFormatter(logbook.StringFormatter):
        def __call__(self, record, handler):
            if record.channel == "alpha":
                entered.set()
                release.wait(5)
            else:
                release.set()
            return super().__call__(record, handler)

    class ReleasingLock:
        def __init__(self):
            self.lock = threading.RLock()

        def __enter__(self):
            if entered.is_set():
                release.set()
            self.lock.acquire()

        def __exit__(self, *exc_info):
            self.lock.release()

    with closing(logbook.SyslogHandler(address=udp_server.getsockname())) as handler:
        handler.lock = ReleasingLock()
        handler.formatter_class = BlockingFormatter
        handler.format_string = "{record.channel}: {record.message}"
        formatter = handler.formatter

        def send(channel):
            with handler, logbook.Flags(errors="raise"):
                logbook.Logger(channel).warning("message {}", channel)

        with ThreadPoolExecutor(max_workers=2) as executor:
            alpha = executor.submit(send, "alpha")
            assert entered.wait(5)
            executor.submit(send, "beta").result(timeout=5)
            alpha.result(timeout=5)

    assert sorted(receive(udp_server)[1:] for _ in range(2)) == [
        ("alpha", "message alpha\n"),
        ("beta", "message beta\n"),
    ]
    assert handler.formatter is formatter
    assert handler.format_string == "{record.channel}: {record.message}"
    assert handler.application_name is None


class CustomFormatter(logbook.StringFormatter):
    pass


@pytest.mark.parametrize(
    "formatter,app_name,message",
    [
        (CustomFormatter("{record.channel}: {record.message}"), "chan", "hello\n"),
        (lambda record, handler: f"custom {record.message}", "-", "custom hello\n"),
    ],
    ids=["StringFormatter", "callable"],
)
def test_syslog_keeps_attached_formatter(udp_server, formatter, app_name, message):
    with closing(logbook.SyslogHandler(address=udp_server.getsockname())) as handler:
        handler.formatter = formatter
        with handler, logbook.Flags(errors="raise"):
            logbook.Logger("chan").warning("hello")
        assert handler.formatter is formatter
    assert receive(udp_server)[1:] == (app_name, message)


def test_syslog_timestamp_is_utc(udp_server, record_time, set_clock):
    set_clock(datetime(2010, 1, 1, 12, tzinfo=timezone.utc))
    with closing(logbook.SyslogHandler(address=udp_server.getsockname())) as handler:
        with handler, logbook.Flags(errors="raise"):
            logbook.Logger("chan").warning("hello")
    assert receive(udp_server)[0] == "2010-01-01T12:00:00Z"
