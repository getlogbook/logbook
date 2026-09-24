import logging
import os
import sys
from contextlib import ExitStack

import pytest

import logbook
from logbook.compat import LoggingHandler, RedirectLoggingHandler

pytestmark = pytest.mark.usefixtures("logging_environment")
EVENT = "request handled"
FIELDS = {"user_id": 42, "request_id": "benchmark-request", "path": "/orders"}
# CodSpeed's simulation mode runs each benchmark once with the simulated CPU
# caches cleared, so a single call mostly measures first-touch cache misses.
# Repeating the call amortises them and measures the per-call cost instead.
ITERATIONS = 1_000


def repeat(fn, *args, **kwargs):
    # A separate loop avoids building an empty kwargs dict on every call.
    if kwargs:
        for _ in range(ITERATIONS):
            fn(*args, **kwargs)
    else:
        for _ in range(ITERATIONS):
            fn(*args)


class LastWriteStream:
    """Avoid accumulating output during benchmark repetitions."""

    def __init__(self):
        self.message = ""

    def write(self, message):
        self.message = message
        return len(message)

    def flush(self):
        pass


@pytest.fixture(scope="session")
def check_speedups():
    if not os.environ.get("DISABLE_LOGBOOK_CEXT_AT_RUNTIME"):
        assert logbook.base._has_speedups, (
            "Logbook speedups are unavailable. Set DISABLE_LOGBOOK_CEXT_AT_RUNTIME=1 "
            "for an intentional fallback run."
        )


@pytest.fixture
def logging_environment(check_speedups):
    # Keep records that no benchmark handler takes away from the default handler.
    with logbook.NullHandler():
        yield


@pytest.fixture
def logger():
    return logbook.Logger("benchmark", level=logbook.DEBUG)


@pytest.fixture
def stream():
    return LastWriteStream()


@pytest.fixture
def handler(stream):
    with logbook.StreamHandler(stream, format_string="{record.message}") as handler:
        yield handler


@pytest.mark.parametrize(
    "filter_type",
    [
        "disabled_logger",
        "logger_level",
        "handler_level",
        "callback_filter",
        "null_handler",
    ],
)
def test_filtered_message(benchmark, logger, stream, filter_type):
    handler = logbook.StreamHandler(stream, format_string="{record.message}")
    if filter_type == "disabled_logger":
        logger.disabled = True
    elif filter_type == "logger_level":
        logger.level = logbook.ERROR
    elif filter_type == "handler_level":
        handler.level = logbook.ERROR
    elif filter_type == "callback_filter":
        handler.filter = lambda record, handler: False
    else:
        handler = logbook.NullHandler()

    with handler:
        benchmark(repeat, logger.info, "request {} handled", 42)

    assert stream.message == ""


@pytest.mark.parametrize("style", ["literal", "positional"])
def test_logging_call(benchmark, logger, handler, stream, style):
    messages = {
        "literal": ("request 42 handled", ()),
        "positional": ("request {} handled", (42,)),
    }
    message, args = messages[style]
    benchmark(repeat, logger.info, message, *args)

    assert stream.message == "request 42 handled\n"


@pytest.mark.parametrize("style", ["default", "default_unicode", "caller"])
def test_record_formatting(benchmark, logger, handler, stream, style):
    if style == "caller":
        handler.format_string = (
            "{record.filename}:{record.lineno}:{record.func_name}: {record.message}"
        )
    else:
        handler.format_string = logbook.StreamHandler.default_format_string
    # Non-ASCII text takes CPython's wider string path through the default format.
    message = "requête traitée ✓" if style == "default_unicode" else EVENT

    def log_event():
        # Keep a caller in this file for the caller-information case.
        for _ in range(ITERATIONS):
            logger.info(message)

    benchmark(log_event)

    if style == "caller":
        assert __file__ in stream.message
        assert ":log_event: request handled\n" in stream.message
    else:
        assert "INFO" in stream.message
        assert "benchmark" in stream.message
        assert message in stream.message


@pytest.mark.parametrize(
    "bubble,depth",
    [
        pytest.param(False, 10, id="first_handler-10"),
        pytest.param(True, 10, id="all_handlers-10"),
    ],
)
def test_handler_stack(benchmark, logger, depth, bubble):
    streams = [LastWriteStream() for _ in range(depth)]
    with ExitStack() as stack:
        for stream in streams:
            stack.enter_context(
                logbook.StreamHandler(
                    stream, format_string="{record.message}", bubble=bubble
                )
            )

        # Warm the handler-stack cache before timing dispatch.
        logger.info(EVENT)
        for stream in streams:
            stream.message = ""
        benchmark(repeat, logger.info, EVENT)

    assert streams[-1].message == EVENT + "\n"
    for stream in streams[:-1]:
        assert stream.message == (EVENT + "\n" if bubble else "")


def test_logger_handler_dispatch(benchmark, logger, stream):
    handler = logbook.StreamHandler(stream, format_string="{record.message}")
    logger.handlers.append(handler)
    try:
        logger.info(EVENT)
        stream.message = ""
        benchmark(repeat, logger.info, EVENT)
    finally:
        logger.handlers.remove(handler)
        handler.close()
    assert stream.message == EVENT + "\n"


@pytest.mark.parametrize("filter_type", ["handler_level", "callback_filter"])
def test_skipped_handlers(benchmark, logger, handler, stream, filter_type):
    with ExitStack() as stack:
        for _ in range(10):
            if filter_type == "handler_level":
                skipped = logbook.NullHandler(level=logbook.ERROR)
            else:
                skipped = logbook.NullHandler(filter=lambda record, handler: False)
            stack.enter_context(skipped)

        logger.info(EVENT)
        stream.message = ""
        benchmark(repeat, logger.info, EVENT)

    assert stream.message == EVENT + "\n"


def test_introspection_disabled(benchmark, logger, handler, stream):
    with logbook.Flags(introspection=False):
        benchmark(repeat, logger.info, EVENT)

    assert stream.message == EVENT + "\n"


def test_handler_push_pop(benchmark, logger, stream):
    handler = logbook.StreamHandler(stream, format_string="{record.message}")

    def request():
        with handler:
            logger.info(EVENT)

    benchmark(repeat, request)

    assert stream.message == EVENT + "\n"


@pytest.mark.parametrize("source", ["extra", "processor"])
def test_record_extra(benchmark, logger, handler, stream, source):
    handler.format_string = "{record.extra[request_id]}: {record.message}"

    def inject(record):
        record.extra.update(FIELDS)

    if source == "extra":
        benchmark(repeat, logger.info, EVENT, extra=FIELDS)
    else:
        with logbook.Processor(inject):
            benchmark(repeat, logger.info, EVENT)

    assert stream.message == "benchmark-request: request handled\n"


def test_processor_push_pop(benchmark, logger, handler, stream):
    handler.format_string = "{record.extra[request_id]}: {record.message}"

    def inject(record):
        record.extra.update(FIELDS)

    processor = logbook.Processor(inject)

    def request():
        with processor:
            logger.info(EVENT)

    benchmark(repeat, request)

    assert stream.message == "benchmark-request: request handled\n"


def test_nested_setup_push_pop(benchmark, logger, stream):
    def inject(record):
        record.extra.update(FIELDS)

    setup = logbook.NestedSetup(
        [
            logbook.StreamHandler(
                stream, format_string="{record.extra[request_id]}: {record.message}"
            ),
            logbook.Processor(inject),
        ]
    )

    def request():
        with setup:
            logger.info(EVENT)

    benchmark(repeat, request)

    assert stream.message == "benchmark-request: request handled\n"


def test_fingers_crossed_buffered(benchmark, logger, stream):
    target = logbook.StreamHandler(stream, format_string="{record.message}")
    with logbook.FingersCrossedHandler(target, buffer_size=100) as handler:
        benchmark(repeat, logger.info, EVENT)

    assert stream.message == ""
    assert len(handler.buffered_records) == 100


def test_record_export(benchmark, logger):
    class ExportHandler(logbook.Handler):
        def emit(self, record):
            self.record = record.to_dict(json_safe=True)

    with ExportHandler() as handler:

        def log_event():
            for _ in range(ITERATIONS):
                logger.info(EVENT)

        benchmark(log_event)

    assert handler.record["message"] == EVENT
    assert handler.record["filename"] == __file__
    assert handler.record["func_name"] == "log_event"
    assert isinstance(handler.record["time"], str)
    assert not {"frame", "calling_frame", "exc_info"} & handler.record.keys()


def _raise_error():
    raise ValueError("benchmark failure")


def _call_error():
    _raise_error()


def test_exception_formatting(benchmark, logger, handler, stream):
    try:
        _call_error()
    except ValueError:
        exc_info = sys.exc_info()

    def log_exceptions():
        # Traceback formatting dwarfs a plain call; fewer iterations keep runs short.
        for _ in range(ITERATIONS // 10):
            logger.exception("cannot handle request", exc_info=exc_info)

    benchmark(log_exceptions)

    assert "ValueError: benchmark failure" in stream.message
    assert "cannot handle request" in stream.message


@pytest.mark.parametrize("direction", ["from_stdlib", "to_stdlib"])
def test_stdlib_redirection(benchmark, logger, stream, direction):
    stdlib_logger = logging.Logger("benchmark", level=logging.DEBUG)
    stdlib_logger.propagate = False
    if direction == "from_stdlib":
        stdlib_handler = RedirectLoggingHandler()
        logbook_handler = logbook.StreamHandler(
            stream,
            format_string="{record.channel}:{record.level_name}:{record.message}",
        )
        source = stdlib_logger
        message = "request %s handled"
    else:
        stdlib_handler = logging.StreamHandler(stream)
        stdlib_handler.setFormatter(
            logging.Formatter("%(name)s:%(levelname)s:%(message)s")
        )
        logbook_handler = LoggingHandler(stdlib_logger)
        source = logger
        message = "request {} handled"
    stdlib_logger.addHandler(stdlib_handler)
    try:
        with logbook_handler:
            benchmark(repeat, source.info, message, 42)
    finally:
        stdlib_logger.removeHandler(stdlib_handler)
        stdlib_handler.close()
    assert stream.message == "benchmark:INFO:request 42 handled\n"
