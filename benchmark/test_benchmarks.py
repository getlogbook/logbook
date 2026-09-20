"""CodSpeed benchmarks.

CI runs these in CodSpeed's simulation mode. To time them locally, run
``nox -s codspeed -- --codspeed-mode=walltime``.

Simulation runs each benchmark once with the simulated CPU caches cleared, so
a single call mostly measures first-touch cache misses. Each benchmark
therefore calls logbook ``ITERATIONS`` times in a plain loop, without a
wrapper per call, so the result reflects the per-call cost of logbook's code.
"""

# Most applications import these, directly or through a framework. Importing
# them here fixes the paths that check for them, such as
# LogRecord.process_name, whatever the benchmark dependencies import.
import asyncio  # noqa: F401
import logging
import multiprocessing  # noqa: F401
import os
import sys
from contextlib import ExitStack

import pytest

import logbook
from logbook.compat import LoggingHandler, RedirectLoggingHandler

pytestmark = pytest.mark.usefixtures("logging_environment")
EVENT = "request handled"
FIELDS = {"user_id": 42, "request_id": "benchmark-request", "path": "/orders"}
ITERATIONS = 1_000


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
    # Pushed application-wide like an application's own setup, on top of the
    # default StderrHandler, to keep records no benchmark handler takes.
    with logbook.NullHandler().applicationbound():
        yield


@pytest.fixture
def logger():
    # Leave the level unset, like a typical Logger(__name__).
    return logbook.Logger("benchmark")


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
        "logger_group_level",
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
    elif filter_type == "logger_group_level":
        logbook.LoggerGroup([logger], level=logbook.ERROR)
    elif filter_type == "handler_level":
        handler.level = logbook.ERROR
    elif filter_type == "callback_filter":
        handler.filter = lambda record, handler: False

    def log_events():
        for _ in range(ITERATIONS):
            logger.info("request {} handled", 42)

    with ExitStack() as stack:
        stack.enter_context(handler)
        if filter_type == "null_handler":
            # Swallows records before they reach the stream handler below.
            stack.enter_context(logbook.NullHandler())
        benchmark(log_events)

    assert stream.message == ""


@pytest.mark.parametrize("style", ["literal", "positional"])
def test_logging_call(benchmark, logger, handler, stream, style):
    if style == "literal":

        def log_events():
            for _ in range(ITERATIONS):
                logger.info("request 42 handled")

    else:

        def log_events():
            for _ in range(ITERATIONS):
                logger.info("request {} handled", 42)

    benchmark(log_events)

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

    def log_events():
        for _ in range(ITERATIONS):
            logger.info(message)

    benchmark(log_events)

    if style == "caller":
        assert __file__ in stream.message
        assert ":log_events: request handled\n" in stream.message
    else:
        assert "INFO" in stream.message
        assert "benchmark" in stream.message
        assert message in stream.message


def test_application_handler(benchmark, logger, stream):
    # The setup the docs teach: a handler pushed application-wide, with the
    # default format.
    def log_events():
        for _ in range(ITERATIONS):
            logger.info(EVENT)

    with logbook.StreamHandler(stream).applicationbound():
        benchmark(log_events)

    assert stream.message.endswith(f"INFO: benchmark: {EVENT}\n")


def test_handler_stack_bubbling(benchmark, logger):
    streams = [LastWriteStream() for _ in range(10)]

    def log_events():
        for _ in range(ITERATIONS):
            logger.info(EVENT)

    with ExitStack() as stack:
        for stream in streams:
            stack.enter_context(
                logbook.StreamHandler(
                    stream, format_string="{record.message}", bubble=True
                )
            )
        benchmark(log_events)

    assert all(stream.message == EVENT + "\n" for stream in streams)


def test_logger_handler_dispatch(benchmark, logger, stream):
    handler = logbook.StreamHandler(stream, format_string="{record.message}")

    def log_events():
        for _ in range(ITERATIONS):
            logger.info(EVENT)

    logger.handlers.append(handler)
    try:
        benchmark(log_events)
    finally:
        logger.handlers.remove(handler)
        handler.close()
    assert stream.message == EVENT + "\n"


@pytest.mark.parametrize("filter_type", ["handler_level", "callback_filter"])
def test_skipped_handlers(benchmark, logger, handler, stream, filter_type):
    def log_events():
        for _ in range(ITERATIONS):
            logger.info(EVENT)

    with ExitStack() as stack:
        for _ in range(10):
            if filter_type == "handler_level":
                skipped = logbook.NullHandler(level=logbook.ERROR)
            else:
                skipped = logbook.NullHandler(filter=lambda record, handler: False)
            stack.enter_context(skipped)
        benchmark(log_events)

    assert stream.message == EVENT + "\n"


class DispatchHandler(logbook.NullHandler):
    """Takes every record without formatting or writing it."""

    blackhole = False
    has_frame = None

    def emit(self, record):
        self.has_frame = record.frame is not None


@pytest.mark.parametrize(
    "introspection", [True, False], ids=["introspection", "no_introspection"]
)
def test_record_dispatch(benchmark, logger, introspection):
    def log_events():
        for _ in range(ITERATIONS):
            logger.info(EVENT)

    with ExitStack() as stack:
        if not introspection:
            stack.enter_context(logbook.Flags(introspection=False))
        handler = stack.enter_context(DispatchHandler())
        benchmark(log_events)

    assert handler.has_frame is introspection


def test_context_stack_iteration(benchmark):
    handlers = [logbook.StreamHandler(LastWriteStream()) for _ in range(3)]
    iter_handlers = logbook.Handler.stack_manager.iter_context_objects

    def iterate_stack():
        # Only the lookup of the cached merged stack; walking the result is
        # plain tuple iteration.
        for _ in range(ITERATIONS):
            iter_handlers()

    with ExitStack() as stack:
        for handler in handlers:
            stack.enter_context(handler)
        benchmark(iterate_stack)
        innermost = list(iter_handlers())[:3]

    assert innermost == handlers[::-1]


def test_logger_creation(benchmark):
    def create_loggers():
        for _ in range(ITERATIONS):
            logbook.Logger("benchmark")

    benchmark(create_loggers)


@pytest.mark.parametrize("scope", ["context", "application", "interleaved"])
def test_handler_push_pop(benchmark, logger, stream, scope):
    handler = logbook.StreamHandler(stream, format_string="{record.message}")
    if scope == "application":

        def log_events():
            for _ in range(ITERATIONS):
                with handler.applicationbound():
                    logger.info(EVENT)

    else:

        def log_events():
            for _ in range(ITERATIONS):
                with handler:
                    logger.info(EVENT)

    with ExitStack() as stack:
        if scope == "interleaved":
            # An application push newer than a context push, so merging the
            # two stacks alternates between them.
            stack.enter_context(logbook.NullHandler(level=logbook.ERROR))
            stack.enter_context(
                logbook.NullHandler(level=logbook.ERROR).applicationbound()
            )
        benchmark(log_events)

    assert stream.message == EVENT + "\n"


@pytest.mark.parametrize("source", ["extra", "processor", "logger_group"])
def test_record_extra(benchmark, logger, handler, stream, source):
    handler.format_string = "{record.extra[request_id]}: {record.message}"

    def inject(record):
        record.extra.update(FIELDS)

    if source == "extra":

        def log_events():
            for _ in range(ITERATIONS):
                logger.info(EVENT, extra=FIELDS)

    else:

        def log_events():
            for _ in range(ITERATIONS):
                logger.info(EVENT)

    with ExitStack() as stack:
        if source == "processor":
            stack.enter_context(logbook.Processor(inject))
        elif source == "logger_group":
            logbook.LoggerGroup([logger], processor=inject)
        benchmark(log_events)

    assert stream.message == "benchmark-request: request handled\n"


def test_processor_push_pop(benchmark, logger, handler, stream):
    handler.format_string = "{record.extra[request_id]}: {record.message}"

    def inject(record):
        record.extra.update(FIELDS)

    processor = logbook.Processor(inject)

    def log_events():
        for _ in range(ITERATIONS):
            with processor:
                logger.info(EVENT)

    benchmark(log_events)

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

    def log_events():
        for _ in range(ITERATIONS):
            with setup:
                logger.info(EVENT)

    benchmark(log_events)

    assert stream.message == "benchmark-request: request handled\n"


def test_fingers_crossed_buffered(benchmark, logger, stream):
    target = logbook.StreamHandler(stream, format_string="{record.message}")

    def log_events():
        for _ in range(ITERATIONS):
            logger.info(EVENT)

    with logbook.FingersCrossedHandler(target, buffer_size=100) as handler:
        benchmark(log_events)

    assert stream.message == ""
    assert len(handler.buffered_records) == 100


@pytest.mark.parametrize(
    "handler_class",
    [
        logbook.FileHandler,
        logbook.RotatingFileHandler,
        logbook.TimedRotatingFileHandler,
    ],
    ids=lambda handler_class: handler_class.__name__,
)
def test_file_handler(benchmark, logger, tmp_path, handler_class):
    # Simulation leaves the write syscalls out, so this measures the handler's
    # own work per emit. Rollover is deliberately not benchmarked.
    kwargs = {}
    if handler_class is logbook.RotatingFileHandler:
        kwargs["max_size"] = sys.maxsize

    def log_events():
        for _ in range(ITERATIONS):
            logger.info(EVENT)

    with handler_class(
        tmp_path / "app.log", format_string="{record.message}", **kwargs
    ):
        benchmark(log_events)

    # The timed handler names its file after the date; take the newest.
    path = sorted(tmp_path.iterdir())[-1]
    assert path.read_text(encoding="utf-8").endswith(EVENT + "\n")


def test_record_export(benchmark, logger):
    class ExportHandler(logbook.Handler):
        def emit(self, record):
            self.record = record.to_dict(json_safe=True)

    def log_events():
        for _ in range(ITERATIONS):
            logger.info(EVENT)

    with ExportHandler() as handler:
        benchmark(log_events)

    assert handler.record["message"] == EVENT
    assert handler.record["filename"] == __file__
    assert handler.record["func_name"] == "log_events"
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
        # Mostly traceback.format_exception, so this mainly catches logbook
        # doing that work more than once. It's slow, so fewer iterations.
        for _ in range(ITERATIONS // 10):
            logger.exception("cannot handle request", exc_info=exc_info)

    benchmark(log_exceptions)

    assert "ValueError: benchmark failure" in stream.message
    assert "cannot handle request" in stream.message


@pytest.mark.parametrize(
    "direction", ["from_stdlib", "from_stdlib_filtered", "to_stdlib"]
)
def test_stdlib_redirection(benchmark, logger, stream, direction):
    stdlib_logger = logging.Logger("benchmark", level=logging.DEBUG)
    stdlib_logger.propagate = False
    if direction == "to_stdlib":
        stdlib_handler = logging.StreamHandler(stream)
        stdlib_handler.setFormatter(
            logging.Formatter("%(name)s:%(levelname)s:%(message)s")
        )
        logbook_handler = LoggingHandler(stdlib_logger)
        log = logger.info
        message = "request {} handled"
    else:
        stdlib_handler = RedirectLoggingHandler()
        logbook_handler = logbook.StreamHandler(
            stream,
            format_string="{record.channel}:{record.level_name}:{record.message}",
        )
        log = stdlib_logger.info
        message = "request %s handled"
        if direction == "from_stdlib_filtered":
            # redirect_logging() sets the stdlib root level to DEBUG, so a
            # library's debug records reach logbook before a handler drops them.
            logbook_handler.level = logbook.INFO
            log = stdlib_logger.debug

    def log_events():
        for _ in range(ITERATIONS):
            log(message, 42)

    stdlib_logger.addHandler(stdlib_handler)
    try:
        with logbook_handler:
            benchmark(log_events)
            if direction == "from_stdlib_filtered":
                assert stream.message == ""
                # The same setup still delivers records at the handler's level.
                stdlib_logger.info(message, 42)
    finally:
        stdlib_logger.removeHandler(stdlib_handler)
        stdlib_handler.close()
    assert stream.message == "benchmark:INFO:request 42 handled\n"
