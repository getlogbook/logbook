from datetime import datetime

import logbook

import pytest

from .utils import get_total_delta_seconds


def test_timedate_format(activation_strategy, logger):
    """
    tests the logbook.set_datetime_format() function
    """
    FORMAT_STRING = '{record.time:%H:%M:%S.%f} {record.message}'
    handler = logbook.TestHandler(format_string=FORMAT_STRING)
    with activation_strategy(handler):
        logbook.set_datetime_format('utc')
        try:
            logger.warn('This is a warning.')
            time_utc = handler.records[0].time
            logbook.set_datetime_format('local')
            logger.warn('This is a warning.')
            time_local = handler.records[1].time
        finally:
            # put back the default time factory
            logbook.set_datetime_format('utc')

    # get the expected difference between local and utc time
    t1 = datetime.now()
    t2 = datetime.utcnow()

    tz_minutes_diff = get_total_delta_seconds(t1 - t2)/60.0

    if abs(tz_minutes_diff) < 1:
        pytest.skip('Cannot test utc/localtime differences '
                    'if they vary by less than one minute...')

    # get the difference between LogRecord local and utc times
    logbook_minutes_diff = get_total_delta_seconds(time_local - time_utc)/60.0
    assert abs(logbook_minutes_diff) > 1, ('Localtime does not differ from UTC by more than 1 '
                                           'minute (Local: %s, UTC: %s)' % (time_local, time_utc))

    ratio = logbook_minutes_diff / tz_minutes_diff

    assert ratio > 0.99
    assert ratio < 1.01
