from datetime import datetime, timedelta, tzinfo

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
    assert abs(logbook_minutes_diff) > 1, (
        'Localtime does not differ from UTC by more than 1 '
        'minute (Local: %s, UTC: %s)' % (time_local, time_utc))

    ratio = logbook_minutes_diff / tz_minutes_diff

    assert ratio > 0.99
    assert ratio < 1.01


def test_tz_aware(activation_strategy, logger):
    """
    tests logbook.set_datetime_format() with a time zone aware time factory
    """
    class utc(tzinfo):
        def tzname(self, dt):
            return 'UTC'
        def utcoffset(self, dt):
            return timedelta(seconds=0)
        def dst(self, dt):
            return timedelta(seconds=0)

    utc = utc()

    def utc_tz():
        return datetime.now(tz=utc)

    FORMAT_STRING = '{record.time:%H:%M:%S.%f%z} {record.message}'
    handler = logbook.TestHandler(format_string=FORMAT_STRING)
    with activation_strategy(handler):
        logbook.set_datetime_format(utc_tz)
        try:
            logger.warn('this is a warning.')
            record = handler.records[0]
        finally:
            # put back the default time factory
            logbook.set_datetime_format('utc')

    assert record.time.tzinfo is not None


def test_invalid_time_factory():
    """
    tests logbook.set_datetime_format() with an invalid time factory callable
    """
    def invalid_factory():
        return False

    with pytest.raises(ValueError) as e:
        try:
            logbook.set_datetime_format(invalid_factory)
        finally:
            # put back the default time factory
            logbook.set_datetime_format('utc')

    assert 'Invalid callable value' in str(e.value)
