import os
import re
import socket
from contextlib import closing

import logbook
from logbook.helpers import u

import pytest

unix_socket = "/tmp/__unixsock_logbook.test"

to_test = [
    (socket.AF_INET, socket.SOCK_DGRAM, ('127.0.0.1', 0)),
    (socket.AF_INET, socket.SOCK_STREAM, ('127.0.0.1', 0)),
]
if hasattr(socket, 'AF_UNIX'):
    to_test.append((socket.AF_UNIX, socket.SOCK_DGRAM, unix_socket))

@pytest.mark.usefixtures("unix_sock_path")
@pytest.mark.parametrize("sock_family,socktype,address", to_test)
def test_syslog_handler(logger, activation_strategy,
                        sock_family, socktype, address):
    delimiter = {socket.AF_UNIX: '\x00',
                 socket.AF_INET: '\n'}[sock_family]
    with closing(socket.socket(sock_family, socktype)) as inc:
        inc.bind(address)
        if socktype == socket.SOCK_STREAM:
            inc.listen(0)
        inc.settimeout(1)
        for app_name in [None, 'Testing']:
            if sock_family == socket.AF_UNIX:
                expected = (r'^<12>%stestlogger: Syslog is weird%s$' %
                            (app_name + ':' if app_name else '',
                             delimiter))
            else:
                expected = (r'^<12>1 \d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?Z %s %s %d '
                            '- - %sSyslog is weird%s$' %
                            (socket.gethostname(),
                             app_name if app_name else 'testlogger',
                             os.getpid(), 'testlogger: ' if app_name else '',
                             delimiter))

            handler = logbook.SyslogHandler(app_name, inc.getsockname(),
                                            socktype=socktype)
            with activation_strategy(handler):
                logger.warn('Syslog is weird')
            try:
                if socktype == socket.SOCK_STREAM:
                    with closing(inc.accept()[0]) as inc2:
                        rv = inc2.recv(1024)
                else:
                    rv = inc.recvfrom(1024)[0]
            except socket.error:
                assert False, 'got timeout on socket'
            rv = rv.decode('utf-8')
            assert re.match(expected, rv), \
                'expected {}, got {}'.format(expected, rv)


@pytest.fixture
def unix_sock_path(request):
    returned = unix_socket

    @request.addfinalizer
    def cleanup():
        if os.path.exists(returned):
            os.unlink(returned)
    return returned
