"""Benchmarks for the interoperability with the stdlib ``logging`` module."""

import logging
from io import StringIO

import pytest

from logbook import StreamHandler
from logbook.compat import LoggingHandler, redirected_logging

ITERATIONS = 500


@pytest.fixture
def stdlib_logger():
    logger = logging.getLogger("Test logger")
    old_handlers = logger.handlers[:]
    yield logger
    logger.handlers[:] = old_handlers


def test_redirect_to_logging(benchmark, logger, stdlib_logger):
    """Logbook records are forwarded to the stdlib logging system."""
    out = StringIO()
    stdlib_logger.addHandler(logging.StreamHandler(out))

    def run():
        for _ in range(ITERATIONS):
            logger.warning("this is handled")

    with LoggingHandler(logger=stdlib_logger):
        benchmark(run)

    assert out.getvalue()


def test_redirect_from_logging(benchmark, stdlib_logger):
    """Stdlib logging records are forwarded to Logbook."""
    out = StringIO()

    def run():
        for _ in range(ITERATIONS):
            stdlib_logger.warning("this is handled")

    with redirected_logging(), StreamHandler(out):
        benchmark(run)

    assert out.getvalue()
