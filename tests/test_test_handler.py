import re


def test_regex_matching(active_handler, logger):
    logger.warn('Hello World!')
    assert active_handler.has_warning(re.compile('^Hello'))
    assert (not active_handler.has_warning(re.compile('world$')))
    assert (not active_handler.has_warning('^Hello World'))


def test_test_handler_cache(active_handler, logger):
    logger.warn('First line')
    assert len(active_handler.formatted_records) == 1
    # store cache, to make sure it is identifiable
    cache = active_handler.formatted_records
    assert len(active_handler.formatted_records) == 1
    assert cache is active_handler.formatted_records
    logger.warn('Second line invalidates cache')
    assert len(active_handler.formatted_records) == 2
    assert (cache is not active_handler.formatted_records)
