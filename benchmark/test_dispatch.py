"""Benchmarks for the log record dispatch path.

These cover the code that runs on every single log call, including the cases
where the record is discarded early (disabled logger, level too low, filtered
out) and the cases where a record is created and handed over to a handler.
"""

from contextlib import ExitStack
from io import StringIO

from logbook import ERROR, Flags, Handler, Logger, NullHandler, Processor, StreamHandler

ITERATIONS = 500


class DummyHandler(Handler):
    """A handler that consumes records without writing them anywhere.

    ``NullHandler`` is a blackhole and short circuits the dispatch machinery,
    so it cannot be used to measure what happens once a record is created.
    """


def test_logger_creation(benchmark):
    def run():
        for _ in range(ITERATIONS):
            Logger("Test")

    benchmark(run)


def test_noop(benchmark, logger):
    """No handler wants the record: it is dropped as early as possible."""
    out = StringIO()

    def run():
        for _ in range(ITERATIONS):
            logger.warning("this is not handled")

    with NullHandler(), StreamHandler(out, level=ERROR):
        benchmark(run)

    assert not out.getvalue()


def test_logger_level_too_low(benchmark, logger):
    """The logger level rejects the record before it is created."""
    out = StringIO()
    logger.level = ERROR

    def run():
        for _ in range(ITERATIONS):
            logger.warning("this is not handled")

    with StreamHandler(out):
        benchmark(run)

    assert not out.getvalue()


def test_disabled_logger(benchmark, logger):
    out = StringIO()
    logger.disable()

    def run():
        for _ in range(ITERATIONS):
            logger.warning("this is not handled")

    with StreamHandler(out):
        benchmark(run)

    assert not out.getvalue()


def test_noop_filter(benchmark, logger):
    """A record is created but rejected by a handler filter."""
    out = StringIO()

    def run():
        for _ in range(ITERATIONS):
            logger.warning("this is not handled")

    with NullHandler(), StreamHandler(out, filter=lambda r, h: False):
        benchmark(run)

    assert not out.getvalue()


def test_noop_filter_on_handler(benchmark, logger):
    """Like :func:`test_noop_filter`, but with ``should_handle`` overridden."""
    out = StringIO()

    class CustomStreamHandler(StreamHandler):
        def should_handle(self, record):
            return False

    def run():
        for _ in range(ITERATIONS):
            logger.warning("this is not handled")

    with NullHandler(), CustomStreamHandler(out):
        benchmark(run)

    assert not out.getvalue()


def test_introspection_enabled(benchmark, logger):
    """Frame introspection is the expensive part of record creation."""

    def run():
        for _ in range(ITERATIONS):
            logger.warning("this is not handled")

    with Flags(introspection=True), DummyHandler():
        benchmark(run)


def test_introspection_disabled(benchmark, logger):
    def run():
        for _ in range(ITERATIONS):
            logger.warning("this is not handled")

    with Flags(introspection=False), DummyHandler():
        benchmark(run)


def test_record_with_args(benchmark, logger):
    """Message formatting is deferred until a handler needs the message."""

    def run():
        for _ in range(ITERATIONS):
            logger.warning("this is {} handled", "not")

    with DummyHandler():
        benchmark(run)


def test_processor(benchmark, logger):
    """A processor injects extra information into every record."""

    def inject_extra(record):
        record.extra["ip"] = "127.0.0.1"

    def run():
        for _ in range(ITERATIONS):
            logger.warning("this is not handled")

    with Processor(inject_extra), DummyHandler():
        benchmark(run)


def test_bubbling_handlers(benchmark, logger):
    """Records bubble through a stack of handlers that all inspect them."""
    out = StringIO()

    def run():
        for _ in range(ITERATIONS):
            logger.warning("this is handled")

    handlers = [
        NullHandler(),
        StreamHandler(out, level=ERROR, bubble=True),
        DummyHandler(bubble=True),
        StreamHandler(out, bubble=True),
    ]
    with ExitStack() as stack:
        for handler in handlers:
            stack.enter_context(handler)
        benchmark(run)

    assert out.getvalue()
