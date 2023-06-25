import os
import re
import socket
from contextlib import closing

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
            inc.listen(0)

        inc.settimeout(1)

        if UNIX_SOCKET_AVAILABLE and sock_family == socket.AF_UNIX:
            expected = r"^<12>{}testlogger: Syslog is weird{}$".format(
                app_name + ":" if app_name else "", delimiter
            )
        else:
            expected = (
                r"^<12>1 \d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?Z %s %s %d - - %sSyslog is weird%s$"
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
            logger.warn("Syslog is weird")

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
