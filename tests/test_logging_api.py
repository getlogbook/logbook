import pickle
import sys

import logbook
from logbook.helpers import iteritems, xrange, u

import pytest


def test_basic_logging(active_handler, logger):
    logger.warn('This is a warning.  Nice hah?')

    assert active_handler.has_warning('This is a warning.  Nice hah?')
    assert active_handler.formatted_records == [
        '[WARNING] testlogger: This is a warning.  Nice hah?']


def test_exception_catching(active_handler, logger):
    assert not active_handler.has_error()
    try:
        1 / 0
    except Exception:
        logger.exception()
    try:
        1 / 0
    except Exception:
        logger.exception('Awesome')
    assert active_handler.has_error('Uncaught exception occurred')
    assert active_handler.has_error('Awesome')
    assert active_handler.records[0].exc_info is not None
    assert '1 / 0' in active_handler.records[0].formatted_exception


def test_exception_catching_with_unicode():
    """ See https://github.com/getlogbook/logbook/issues/104
    """
    try:
        raise Exception(u('\u202a test \u202c'))
    except:
        r = logbook.LogRecord('channel', 'DEBUG', 'test',
                              exc_info=sys.exc_info())
    r.exception_message


@pytest.mark.parametrize('as_tuple', [True, False])
def test_exc_info(as_tuple, logger, active_handler):
    try:
        1 / 0
    except Exception:
        exc_info = sys.exc_info()
        logger.info("Exception caught",
                    exc_info=exc_info if as_tuple else True)
    assert active_handler.records[0].exc_info is not None
    assert active_handler.records[0].exc_info == exc_info


def test_to_dict(logger, active_handler):
    try:
        1 / 0
    except Exception:
        logger.exception()
        record = active_handler.records[0]

    exported = record.to_dict()
    record.close()
    imported = logbook.LogRecord.from_dict(exported)
    for key, value in iteritems(record.__dict__):
        if key[0] == '_':
            continue
        assert value == getattr(imported, key)


def test_pickle(active_handler, logger):
    try:
        1 / 0
    except Exception:
        logger.exception()
        record = active_handler.records[0]
    record.pull_information()
    record.close()

    for p in xrange(pickle.HIGHEST_PROTOCOL):
        exported = pickle.dumps(record, p)
        imported = pickle.loads(exported)
        for key, value in iteritems(record.__dict__):
            if key[0] == '_':
                continue
            imported_value = getattr(imported, key)
            if isinstance(value, ZeroDivisionError):
                # in Python 3.2, ZeroDivisionError(x) != ZeroDivisionError(x)
                assert type(value) is type(imported_value)
                assert value.args == imported_value.args
            else:
                assert value == imported_value
