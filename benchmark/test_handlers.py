"""Benchmarks for the handlers that actually emit records.

This measures the formatting and writing side of Logbook: turning a record
into a line of text and pushing it to a stream, a file or an in-memory buffer.
"""

from io import StringIO

from logbook import (
    ERROR,
    FileHandler,
    FingersCrossedHandler,
    GroupHandler,
    StreamHandler,
    StringFormatter,
)
from logbook import TestHandler as LogbookTestHandler

ITERATIONS = 500


def test_stream_handler(benchmark, logger):
    out = StringIO()

    def run():
        for _ in range(ITERATIONS):
            logger.warning("this is handled")

    with StreamHandler(out):
        benchmark(run)

    assert out.getvalue()


def test_stream_handler_custom_format(benchmark, logger):
    out = StringIO()
    format_string = (
        "{record.time:%Y-%m-%d %H:%M:%S.%f} {record.level_name}: "
        "{record.channel}: {record.message} [{record.extra[ip]}]"
    )

    def run():
        for _ in range(ITERATIONS):
            logger.warning("this is handled", extra={"ip": "127.0.0.1"})

    with StreamHandler(out, format_string=format_string):
        benchmark(run)

    assert out.getvalue()


def test_file_handler(benchmark, logger, tmp_path):
    filename = str(tmp_path / "logbook.log")

    def run():
        for _ in range(ITERATIONS):
            logger.warning("this is handled")

    with FileHandler(filename):
        benchmark(run)


def test_file_handler_unicode(benchmark, logger, tmp_path):
    filename = str(tmp_path / "logbook-unicode.log")

    def run():
        for _ in range(ITERATIONS):
            logger.warning("this is handled \N{SNOWMAN}")

    with FileHandler(filename):
        benchmark(run)


def test_test_handler(benchmark, logger):
    """The test handler keeps every record around in memory."""

    def run():
        for _ in range(ITERATIONS):
            logger.warning("this is handled")

    with LogbookTestHandler():
        benchmark(run)


def test_fingers_crossed_handler(benchmark, logger):
    """Records are buffered until an error triggers the inner handler."""
    out = StringIO()

    def run():
        for _ in range(ITERATIONS):
            logger.warning("this is buffered")

    with FingersCrossedHandler(StreamHandler(out), action_level=ERROR, buffer_size=128):
        benchmark(run)

    assert not out.getvalue()


def test_group_handler(benchmark, logger):
    """Records are collected and emitted as a single batch on exit."""
    out = StringIO()

    def run():
        for _ in range(ITERATIONS):
            logger.warning("this is handled")

    with GroupHandler(StreamHandler(out)):
        benchmark(run)


def test_formatter(benchmark, logger):
    """Format an already existing record over and over again."""
    handler = LogbookTestHandler()
    with handler:
        logger.warning("this is handled")
    record = handler.records[0]
    formatter = StringFormatter(StreamHandler.default_format_string)

    def run():
        for _ in range(ITERATIONS):
            formatter(record, handler)

    benchmark(run)
