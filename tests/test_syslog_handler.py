import os
import socket
from contextlib import closing

import logbook
from logbook.helpers import u

import pytest


def test_syslog_handler(logger, activation_strategy, unix_sock_path):
    to_test = [
        (socket.AF_INET, ('127.0.0.1', 0)),
    ]
    if hasattr(socket, 'AF_UNIX'):
        to_test.append((socket.AF_UNIX, unix_sock_path))
    for sock_family, address in to_test:
        with closing(socket.socket(sock_family, socket.SOCK_DGRAM)) as inc:
            inc.bind(address)
            inc.settimeout(1)
            for app_name in [None, 'Testing']:
                handler = logbook.SyslogHandler(app_name, inc.getsockname())
                with activation_strategy(handler):
                    logger.warn('Syslog is weird')
                try:
                    rv = inc.recvfrom(1024)[0]
                except socket.error:
                    assert False, 'got timeout on socket'
                assert rv == (u('<12>%stestlogger: Syslog is weird\x00') %
                              ((app_name and (app_name + u(':'))) or u(''))).encode('utf-8')


@pytest.fixture
def unix_sock_path(request):
    returned = "/tmp/__unixsock_logbook.test"

    @request.addfinalizer
    def cleanup():
        if os.path.exists(returned):
            os.unlink(returned)
    return returned
