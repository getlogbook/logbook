import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

import logbook


class MyObject:
    def __init__(self, logger_func):
        self._logger_func = logger_func

    def __str__(self):
        self._logger_func("this debug message produced in __str__")
        return "<complex object>"


class FakeLock:
    def __init__(self):
        self._acquired = False
        self._deadlock_occurred = False

    def acquire(self):
        if self._acquired:
            self._deadlock_occurred = True
        self._acquired = True

    def release(self):
        self._acquired = False


def test_deadlock_in_emit():
    logbook_logger = logbook.Logger("logbook")
    obj = MyObject(logbook_logger.info)
    stream_handler = logbook.StreamHandler(stream=sys.stderr, level=logbook.DEBUG)
    stream_handler.lock = FakeLock()
    with stream_handler.applicationbound():
        logbook_logger.info("format this: {}", obj)
    assert not stream_handler.lock._deadlock_occurred


def run_fork_scenario(scenario, mode):
    script = Path(__file__).with_name("fork_locks.py")
    with subprocess.Popen(
        [sys.executable, str(script), scenario, mode],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    ) as process:
        try:
            output = process.communicate(timeout=30)[0]
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            output = process.communicate()[0]
    assert process.returncode == 0, output


requires_fork = pytest.mark.skipif(not hasattr(os, "fork"), reason="requires os.fork")


@requires_fork
@pytest.mark.parametrize(
    ("lock", "mode"),
    [
        ("handler", "native"),
        ("handler", "patched"),
        ("rate_limit", "native"),
        ("context_stack", "native"),
    ],
)
def test_lock_held_by_another_thread_at_fork(lock, mode):
    if mode != "native":
        pytest.importorskip("gevent")
    run_fork_scenario(lock, mode)
