"""Fork scenarios for test_deadlock.py, each run in a new interpreter."""

import io
import os
import signal
import sys
import time
import traceback
import warnings
from _thread import allocate_lock, start_new_thread

# Bound before gevent patches them, so the lock holder is a native thread and
# the parent waits for the child without running the hub.
sleep, waitpid = time.sleep, os.waitpid


def fork(child):
    pid = os.fork()
    if pid == 0:
        try:
            child()
        except BaseException:
            traceback.print_exc()
            sys.stderr.flush()
            os._exit(1)
        os._exit(0)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        done, status = waitpid(pid, os.WNOHANG)
        if done:
            assert os.waitstatus_to_exitcode(status) == 0, "child failed"
            return
        sleep(0.01)
    os.kill(pid, signal.SIGKILL)
    waitpid(pid, 0)
    raise AssertionError("child hung")


def fork_while_held(lock, child):
    held, release = allocate_lock(), allocate_lock()
    held.acquire()
    release.acquire()

    def hold():
        with lock:
            held.release()
            release.acquire()

    start_new_thread(hold, ())
    held.acquire()
    try:
        fork(child)
    finally:
        release.release()


def on_new_thread(target):
    done = allocate_lock()
    done.acquire()

    def run():
        target()
        done.release()

    start_new_thread(run, ())
    assert done.acquire(timeout=3), "new thread did not finish"


def main(scenario, mode):
    warnings.simplefilter("ignore", DeprecationWarning)
    if mode == "patched":
        from gevent import monkey

        monkey.patch_all()
    import logbook

    record = logbook.LogRecord("fork", logbook.ERROR, "child")
    record.heavy_init()
    if scenario == "handler":
        stream = io.StringIO()
        handler = logbook.StreamHandler(stream, format_string="{record.message}")

        def child():
            handler.handle(record)
            assert stream.getvalue() == "child\n"
            on_new_thread(lambda: logbook.StreamHandler(io.StringIO()))

        fork_while_held(handler.lock, child)
        on_new_thread(lambda: logbook.StreamHandler(io.StringIO()))
    elif scenario == "rate_limit":
        handler = logbook.MailHandler(
            "sender@example.com", ["sink@example.com"], record_limit=1
        )
        fork_while_held(handler._limit_lock, lambda: handler.check_delivery(record))
    elif scenario == "context_stack":
        from logbook._fallback import ContextStackManager

        manager = ContextStackManager()
        fork_while_held(manager._write_lock, lambda: manager.push_application(1))


if __name__ == "__main__":
    main(*sys.argv[1:])
