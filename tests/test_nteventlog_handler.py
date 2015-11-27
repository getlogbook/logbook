import os

import logbook
import pytest

from .utils import require_module


@require_module('win32con')
@require_module('win32evtlog')
@require_module('win32evtlogutil')
@pytest.mark.skipif(os.environ.get('ENABLE_LOGBOOK_NTEVENTLOG_TESTS') is None,
                    reason="Don't clutter NT Event Log unless enabled.")
def test_nteventlog_handler():
    from win32con import (
        EVENTLOG_ERROR_TYPE, EVENTLOG_INFORMATION_TYPE, EVENTLOG_WARNING_TYPE)
    from win32evtlog import (
        EVENTLOG_BACKWARDS_READ, EVENTLOG_SEQUENTIAL_READ, OpenEventLog,
        ReadEventLog)
    from win32evtlogutil import SafeFormatMessage

    logger = logbook.Logger('Test Logger')

    with logbook.NTEventLogHandler('Logbook Test Suite'):
        logger.info('The info log message.')
        logger.warning('The warning log message.')
        logger.error('The error log message.')

    def iter_event_log(handle, flags, offset):
        while True:
            events = ReadEventLog(handle, flags, offset)
            for event in events:
                yield event
            if not events:
                break

    handle = OpenEventLog(None, 'Application')
    flags = EVENTLOG_BACKWARDS_READ | EVENTLOG_SEQUENTIAL_READ

    for event in iter_event_log(handle, flags, 0):
        source = str(event.SourceName)
        if source == 'Logbook Test Suite':
            message = SafeFormatMessage(event, 'Application')
            if 'Message Level: INFO' in message:
                assert 'The info log message' in message
                assert event.EventType == EVENTLOG_INFORMATION_TYPE
            if 'Message Level: WARNING' in message:
                assert 'The warning log message' in message
                assert event.EventType == EVENTLOG_WARNING_TYPE
            if 'Message Level: ERROR' in message:
                assert 'The error log message' in message
                assert event.EventType == EVENTLOG_ERROR_TYPE
