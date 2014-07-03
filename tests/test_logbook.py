import logbook

import pytest


def test_global_functions(activation_strategy):
    with activation_strategy(logbook.TestHandler()) as handler:
        logbook.debug('a debug message')
        logbook.info('an info message')
        logbook.warn('warning part 1')
        logbook.warning('warning part 2')
        logbook.notice('notice')
        logbook.error('an error')
        logbook.critical('pretty critical')
        logbook.log(logbook.CRITICAL, 'critical too')

    assert handler.has_debug('a debug message')
    assert handler.has_info('an info message')
    assert handler.has_warning('warning part 1')
    assert handler.has_warning('warning part 2')
    assert handler.has_notice('notice')
    assert handler.has_error('an error')
    assert handler.has_critical('pretty critical')
    assert handler.has_critical('critical too')
    assert handler.records[0].channel == 'Generic'
    assert handler.records[0].dispatcher is None


def test_level_lookup_failures():
    with pytest.raises(LookupError):
        logbook.get_level_name(37)
    with pytest.raises(LookupError):
        logbook.lookup_level('FOO')
