import re

import pytest


@pytest.mark.parametrize(
    "level, method",
    [
        ("trace", "has_traces"),
        ("debug", "has_debugs"),
        ("info", "has_infos"),
        ("notice", "has_notices"),
        ("warning", "has_warnings"),
        ("error", "has_errors"),
        ("critical", "has_criticals"),
    ],
)
def test_has_level(active_handler, logger, level, method):
    log = getattr(logger, level)
    log("Hello World")
    assert getattr(active_handler, method)


@pytest.mark.parametrize(
    "level, method",
    [
        ("trace", "has_trace"),
        ("debug", "has_debug"),
        ("info", "has_info"),
        ("notice", "has_notice"),
        ("warning", "has_warning"),
        ("error", "has_error"),
        ("critical", "has_critical"),
    ],
)
def test_regex_matching(active_handler, logger, level, method):
    log = getattr(logger, level)
    log("Hello World")
    has_level_method = getattr(active_handler, method)
    assert has_level_method(re.compile("^Hello"))
    assert not has_level_method(re.compile("world$"))
    assert not has_level_method("^Hello World")


def test_test_handler_cache(active_handler, logger):
    logger.warn("First line")
    assert len(active_handler.formatted_records) == 1
    # store cache, to make sure it is identifiable
    cache = active_handler.formatted_records
    assert len(active_handler.formatted_records) == 1
    assert cache is active_handler.formatted_records
    logger.warn("Second line invalidates cache")
    assert len(active_handler.formatted_records) == 2
    assert cache is not active_handler.formatted_records
