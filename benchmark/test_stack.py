"""Benchmarks for the context stack machinery.

The stack manager is implemented in Rust when the speedups are available (and
in pure Python otherwise), and it is walked for every single log record, so it
is one of the hottest parts of Logbook.
"""

from contextlib import ExitStack
from io import StringIO

from logbook import (
    ERROR,
    WARNING,
    FileHandler,
    Flags,
    Handler,
    NestedSetup,
    NullHandler,
    Processor,
    StreamHandler,
)

ITERATIONS = 100


def test_stack_iteration(benchmark, tmp_path):
    """Walk a stack of three handlers, the way dispatching does."""
    out = StringIO()
    filename = str(tmp_path / "logbook.log")

    def run():
        for _ in range(ITERATIONS):
            list(Handler.stack_manager.iter_context_objects())

    handlers = [
        NullHandler(),
        StreamHandler(out, level=WARNING),
        FileHandler(filename, level=ERROR),
    ]
    with ExitStack() as stack:
        for handler in handlers:
            stack.enter_context(handler)
        benchmark(run)


def test_stack_push_pop(benchmark):
    """Push and pop a handler, which invalidates the stack caches."""
    out = StringIO()
    handler = StreamHandler(out)

    def run():
        for _ in range(ITERATIONS):
            handler.push_context()
            list(Handler.stack_manager.iter_context_objects())
            handler.pop_context()

    with NullHandler():
        benchmark(run)


def test_nested_setup(benchmark, logger):
    """A nested setup is pushed and popped as a single unit."""
    out = StringIO()
    setup = NestedSetup(
        [
            NullHandler(),
            StreamHandler(out, level=ERROR, bubble=True),
            Processor(lambda record: None),
        ]
    )

    def run():
        for _ in range(ITERATIONS):
            with setup:
                logger.warning("this is not handled")

    benchmark(run)

    assert not out.getvalue()


def test_flag_lookup(benchmark):
    """Flags are looked up through their own stack on every record."""

    def run():
        for _ in range(ITERATIONS):
            Flags.get_flag("introspection", True)

    with Flags(errors="silent"), Flags(introspection=False):
        benchmark(run)
