import os
import re
import socket
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, wait
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
    logger,
    activation_strategy,
    sock_family,
    socktype,
    address,
    app_name,
    unix_sock_path,
):
    delimiter = DELIMITERS[sock_family]
    if UNIX_SOCKET_AVAILABLE and sock_family == socket.AF_UNIX:
        address = unix_sock_path
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


@pytest.mark.skipif(not UNIX_SOCKET_AVAILABLE, reason="Requires Unix sockets")
def test_syslog_unix_stream_sends_whole_record(logger, unix_sock_path):
    def receive(server):
        with closing(server.accept()[0]) as connection:
            connection.settimeout(5)
            chunks = []
            while chunk := connection.recv(65536):
                chunks.append(chunk)
            return b"".join(chunks)

    message = "x" * 1_000_000
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(unix_sock_path)
        server.listen()
        server.settimeout(5)
        handler = logbook.SyslogHandler(address=unix_sock_path)
        handler.socket.settimeout(5)
        with ThreadPoolExecutor(max_workers=1) as executor:
            received = executor.submit(receive, server)
            with closing(handler), handler, logbook.Flags(errors="raise"):
                logger.warning(message)
            expected = f"<12>testlogger: {message}\x00".encode()
            assert received.result(timeout=5) == expected


class FakeStream:
    def __init__(self, *args):
        self.closed = False

    def connect(self, address):
        pass

    def getsockname(self):
        return ("127.0.0.1", 12345)

    def close(self):
        self.closed = True


@pytest.mark.parametrize("unix", [False, True])
def test_syslog_stream_retry_sends_whole_record(monkeypatch, unix):
    if unix and not UNIX_SOCKET_AVAILABLE:
        pytest.skip("Requires Unix sockets")
    sockets = []

    class Stream(FakeStream):
        def __init__(self, *args):
            super().__init__()
            self.broken = not sockets
            self.data = b""
            sockets.append(self)

        def send(self, data):
            if self.broken:
                raise BrokenPipeError
            self.data += data[:3]
            return min(len(data), 3)

        def sendall(self, data):
            while data:
                data = data[self.send(data) :]

    monkeypatch.setattr(socket, "socket", Stream)
    handler = logbook.SyslogHandler(
        address="/syslog" if unix else ("127.0.0.1", 514),
        socktype=socket.SOCK_STREAM,
    )
    handler.send_to_socket(b"whole record\n")
    assert sockets[0].closed
    assert sockets[1].data == b"whole record\n"


def test_syslog_serializes_stream_sends(monkeypatch):
    first_started = threading.Event()
    release_first = threading.Event()
    calls = []

    class Stream(FakeStream):
        def sendall(self, data):
            calls.append(("start", data))
            if data == b"first":
                first_started.set()
                release_first.wait(2)
            calls.append(("end", data))

    monkeypatch.setattr(socket, "socket", Stream)
    handler = logbook.SyslogHandler(
        address=("127.0.0.1", 514), socktype=socket.SOCK_STREAM
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(handler.send_to_socket, b"first")
        assert first_started.wait(2)
        second = executor.submit(handler.send_to_socket, b"second")
        try:
            assert not wait([second], timeout=0.2).done
        finally:
            release_first.set()
        first.result(timeout=2)
        second.result(timeout=2)
    assert calls == [
        ("start", b"first"),
        ("end", b"first"),
        ("start", b"second"),
        ("end", b"second"),
    ]


def test_syslog_keeps_multiline_records_together(monkeypatch):
    first_sent = threading.Event()
    second_sent = threading.Event()
    sent = []

    class Stream(FakeStream):
        def sendall(self, data):
            sent.append(data)
            if data == b"c":
                second_sent.set()

    class Lines(logbook.SyslogHandler):
        def net_envelope(self, record):
            return record.message.split("\n")

        def send_to_socket(self, data):
            super().send_to_socket(data)
            if data == b"a":
                first_sent.set()
                second_sent.wait(0.2)

    monkeypatch.setattr(socket, "socket", Stream)
    handler = Lines(address=("127.0.0.1", 514), socktype=socket.SOCK_STREAM)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(
            handler.emit, logbook.LogRecord("app", logbook.WARNING, "a\nb")
        )
        assert first_sent.wait(2)
        second = executor.submit(
            handler.emit, logbook.LogRecord("app", logbook.WARNING, "c\nd")
        )
        first.result(timeout=2)
        second.result(timeout=2)
    assert sent == [b"a", b"b", b"c", b"d"]


@pytest.fixture
def unix_sock_path():
    # The default temporary directory on macOS is too long for AF_UNIX paths.
    parent = "/tmp" if os.name == "posix" and os.path.isdir("/tmp") else None
    with tempfile.TemporaryDirectory(prefix="lb-", dir=parent) as directory:
        yield os.path.join(directory, "socket")


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


@pytest.mark.parametrize("unix", [False, True])
@pytest.mark.parametrize("socktype", [socket.SOCK_DGRAM, socket.SOCK_STREAM])
@pytest.mark.parametrize("message", ["first\nsecond", ""])
def test_syslog_empty_record_delimiter(logger, unix_sock_path, unix, socktype, message):
    if unix and not UNIX_SOCKET_AVAILABLE:
        pytest.skip("Requires Unix sockets")
    family = socket.AF_UNIX if unix else socket.AF_INET
    address = unix_sock_path if unix else ("127.0.0.1", 0)
    with socket.socket(family, socktype) as server:
        server.bind(address)
        server.settimeout(2)
        if socktype == socket.SOCK_STREAM:
            server.listen()
        with closing(
            logbook.SyslogHandler(
                application_name="tests",
                address=server.getsockname(),
                socktype=socktype,
                format_string="{record.message}",
                record_delimiter="",
            )
        ) as handler:
            with handler, logbook.Flags(errors="raise"):
                logger.warning(message)
            if socktype == socket.SOCK_STREAM:
                with closing(server.accept()[0]) as connection:
                    connection.settimeout(2)
                    handler.close()
                    chunks = []
                    while chunk := connection.recv(1024):
                        chunks.append(chunk)
                    received = b"".join(chunks)
            else:
                received = server.recv(1024)
                server.setblocking(False)
                with pytest.raises(BlockingIOError):
                    server.recv(1024)
    body = (
        received.removeprefix(b"<12>tests:") if unix else received.split(b" - - ", 1)[1]
    )
    assert body == message.encode()
