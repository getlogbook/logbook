import json
import os
import threading
import time
from queue import Queue

import pytest

import logbook

from .fork_locks import fork, fork_while_held
from .utils import LETTERS, missing, require_module, unused_tcp_address

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))


@require_module("zmq")
def test_zeromq_handler(logger, handlers, subscriber):
    tests = [
        "Logging something",
        "Something with umlauts äöü",
        "Something else for good measure",
    ]
    for test in tests:
        for handler in handlers:
            with handler:
                logger.warning(test)
                record = subscriber.recv()
                assert record.message == test
                assert record.channel == logger.name


@require_module("zmq")
def test_zeromq_background_thread(logger, handlers, subscriber):
    test_handler = logbook.TestHandler()
    controller = subscriber.dispatch_in_background(test_handler)

    for handler in handlers:
        with handler:
            logger.warning("This is a warning")
            logger.error("This is an error")

    # stop the controller.  This will also stop the loop and join the
    # background process.  Before that we give it a fraction of a second
    # to get all results
    time.sleep(0.5)
    controller.stop()

    assert test_handler.has_warning("This is a warning")
    assert test_handler.has_error("This is an error")


@missing("zmq")
def test_missing_zeromq():
    from logbook.queues import ZeroMQHandler, ZeroMQSubscriber

    with pytest.raises(RuntimeError):
        ZeroMQHandler("tcp://127.0.0.1:42000")
    with pytest.raises(RuntimeError):
        ZeroMQSubscriber("tcp://127.0.0.1:42000")


class MultiProcessingHandlerSendBack:
    def __init__(self, queue):
        self.queue = queue

    def __call__(self):
        from logbook.queues import MultiProcessingHandler

        handler = MultiProcessingHandler(self.queue)
        handler.push_thread()
        try:
            logbook.warning("Hello World")
        finally:
            handler.pop_thread()


@require_module("multiprocessing")
def test_multi_processing_handler():
    if os.getenv("APPVEYOR") == "True":
        pytest.skip("Test hangs on AppVeyor CI")
    from multiprocessing import Process, Queue

    from logbook.queues import MultiProcessingSubscriber

    queue = Queue(-1)
    test_handler = logbook.TestHandler()
    subscriber = MultiProcessingSubscriber(queue)

    p = Process(target=MultiProcessingHandlerSendBack(queue))
    p.start()
    p.join()

    with test_handler:
        subscriber.dispatch_once()
        assert test_handler.has_warning("Hello World")


class BatchTestHandler(logbook.TestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.batches = []

    def emit(self, record):
        super().emit(record)
        self.batches.append([record])

    def emit_batch(self, records, reason):
        for record in records:
            super().emit(record)
        self.batches.append(records)


def test_threaded_wrapper_handler(logger):
    from logbook.queues import ThreadedWrapperHandler

    test_handler = BatchTestHandler()
    with ThreadedWrapperHandler(test_handler) as handler:
        logger.warning("Just testing")
        logger.error("More testing")

    # give it some time to sync up
    handler.close()

    assert not handler.controller.running
    assert len(test_handler.records) == 2
    assert len(test_handler.batches) == 2
    assert all(len(records) == 1 for records in test_handler.batches)
    assert test_handler.has_warning("Just testing")
    assert test_handler.has_error("More testing")


def test_threaded_wrapper_handler_emit():
    from logbook.queues import ThreadedWrapperHandler

    test_handler = BatchTestHandler()
    with ThreadedWrapperHandler(test_handler) as handler:
        lr = logbook.LogRecord("Test Logger", logbook.WARNING, "Just testing")
        test_handler.emit(lr)
        lr = logbook.LogRecord("Test Logger", logbook.ERROR, "More testing")
        test_handler.emit(lr)

    # give it some time to sync up
    handler.close()

    assert not handler.controller.running
    assert len(test_handler.records) == 2
    assert len(test_handler.batches) == 2
    assert all(len(records) == 1 for records in test_handler.batches)
    assert test_handler.has_warning("Just testing")
    assert test_handler.has_error("More testing")


def test_threaded_wrapper_handler_emit_batched():
    from logbook.queues import ThreadedWrapperHandler

    test_handler = BatchTestHandler()
    with ThreadedWrapperHandler(test_handler) as handler:
        test_handler.emit_batch(
            [
                logbook.LogRecord("Test Logger", logbook.WARNING, "Just testing"),
                logbook.LogRecord("Test Logger", logbook.ERROR, "More testing"),
            ],
            "group",
        )

    # give it some time to sync up
    handler.close()

    assert not handler.controller.running
    assert len(test_handler.records) == 2
    assert len(test_handler.batches) == 1
    (records,) = test_handler.batches
    assert len(records) == 2
    assert test_handler.has_warning("Just testing")
    assert test_handler.has_error("More testing")


def test_threaded_wrapper_handler_start_twice():
    from logbook.queues import ThreadedWrapperHandler

    handler = ThreadedWrapperHandler(logbook.TestHandler())
    with pytest.raises(RuntimeError):
        handler.controller.start()
    handler.close()


def test_threaded_wrapper_handler_escalation(logger):
    from logbook.queues import ThreadedWrapperHandler

    test_handler = logbook.TestHandler()
    handler = logbook.FingersCrossedHandler(ThreadedWrapperHandler(test_handler))
    with handler:
        logger.warning("Just testing")
        logger.error("More testing")

    handler.close()

    assert test_handler.has_warning("Just testing")
    assert test_handler.has_error("More testing")


def test_threaded_wrapper_handler_error(logger, capsys):
    from logbook.queues import ThreadedWrapperHandler

    class FailingTestHandler(logbook.TestHandler):
        def emit(self, record):
            if record.msg == "Failing":
                raise ValueError("emit failed")
            super().emit(record)

        def emit_batch(self, records, reason):
            if not records:
                raise ValueError("empty batch")
            super().emit_batch(records, reason)

    test_handler = FailingTestHandler()
    with ThreadedWrapperHandler(test_handler) as handler:
        logger.warning("Failing")
        handler.emit_batch(
            [logbook.LogRecord("Test Logger", logbook.WARNING, "Failing")], "group"
        )
        handler.emit_batch([], "group")
        logger.error("More testing")

    handler.close()

    assert test_handler.has_error("More testing")
    err = capsys.readouterr().err
    assert err.count("ValueError: emit failed") == 2
    assert err.count("Logged from file") == 2


def release_when_close_waits(monkeypatch, handler, release):
    queue_put = handler.queue.put

    def put(item, block=True, timeout=None):
        if block:
            release.set()
        return queue_put(item, block, timeout)

    monkeypatch.setattr(handler.queue, "put", put)


def test_threaded_wrapper_handler_close_full_queue(logger, monkeypatch):
    from logbook.queues import ThreadedWrapperHandler

    started = threading.Event()
    release = threading.Event()

    class BlockingTestHandler(logbook.TestHandler):
        def emit(self, record):
            started.set()
            assert release.wait(5)
            super().emit(record)

    test_handler = BlockingTestHandler()
    with ThreadedWrapperHandler(test_handler, maxsize=1) as handler:
        logger.warning("Just testing")
        assert started.wait(5)
        logger.error("More testing")

    release_when_close_waits(monkeypatch, handler, release)
    handler.close()

    assert test_handler.has_warning("Just testing")
    assert test_handler.has_error("More testing")


def test_threaded_wrapper_handler_close_dead_worker(logger, monkeypatch):
    from logbook.queues import ThreadedWrapperHandler

    started = threading.Event()
    release = threading.Event()

    class SlowFailingTestHandler(logbook.TestHandler):
        def emit(self, record):
            started.set()
            assert release.wait(5)
            raise ValueError("emit failed")

    errors = []
    monkeypatch.setattr(threading, "excepthook", errors.append)
    with logbook.Flags(errors="raise").applicationbound():
        with ThreadedWrapperHandler(SlowFailingTestHandler(), maxsize=1) as handler:
            logger.warning("Just testing")
            assert started.wait(5)
            logger.error("More testing")

        release_when_close_waits(monkeypatch, handler, release)
        closer = threading.Thread(target=handler.close, daemon=True)
        closer.start()
        closer.join(5)
    assert not closer.is_alive()
    handler.close()
    assert [error.exc_type for error in errors] == [ValueError]


def test_threaded_wrapper_handler_close_from_worker(logger):
    from logbook.queues import ThreadedWrapperHandler

    started = threading.Event()
    queued = threading.Event()
    errors = []

    class ClosingTestHandler(logbook.TestHandler):
        def emit(self, record):
            if record.msg == "Close":
                started.set()
                assert queued.wait(5)
                try:
                    handler.close()
                except RuntimeError as e:
                    errors.append(e)
            super().emit(record)

    test_handler = ClosingTestHandler()
    with ThreadedWrapperHandler(test_handler, maxsize=1) as handler:
        logger.warning("Close")
        assert started.wait(5)
        logger.error("More testing")
        queued.set()

    closer = threading.Thread(target=handler.close, daemon=True)
    closer.start()
    closer.join(5)
    assert not closer.is_alive()
    assert len(errors) == 1
    assert test_handler.has_error("More testing")


@require_module("execnet")
def test_execnet_handler():
    def run_on_remote(channel):
        import logbook
        from logbook.queues import ExecnetChannelHandler

        handler = ExecnetChannelHandler(channel)
        log = logbook.Logger("Execnet")
        handler.push_application()
        log.info("Execnet works")

    import execnet

    gw = execnet.makegateway()
    channel = gw.remote_exec(run_on_remote)
    from logbook.queues import ExecnetChannelSubscriber

    subscriber = ExecnetChannelSubscriber(channel)
    record = subscriber.recv()
    assert record.msg == "Execnet works"
    gw.exit()


class SubscriberGroupSendBack:
    def __init__(self, message, queue):
        self.message = message
        self.queue = queue

    def __call__(self):
        from logbook.queues import MultiProcessingHandler

        with MultiProcessingHandler(self.queue):
            logbook.warning(self.message)


@require_module("multiprocessing")
def test_subscriber_group():
    if os.getenv("APPVEYOR") == "True":
        pytest.skip("Test hangs on AppVeyor CI")
    from multiprocessing import Process, Queue

    from logbook.queues import MultiProcessingSubscriber, SubscriberGroup

    a_queue = Queue(-1)
    b_queue = Queue(-1)
    subscriber = SubscriberGroup(
        [MultiProcessingSubscriber(a_queue), MultiProcessingSubscriber(b_queue)]
    )

    for _ in range(10):
        p1 = Process(target=SubscriberGroupSendBack("foo", a_queue))
        p2 = Process(target=SubscriberGroupSendBack("bar", b_queue))
        p1.start()
        p2.start()
        p1.join()
        p2.join()
        messages = [subscriber.recv().message for i in (1, 2)]
        assert sorted(messages) == ["bar", "foo"]


def test_thread_controller_start_twice():
    from logbook.queues import SubscriberGroup

    controller = SubscriberGroup().dispatch_in_background()
    with pytest.raises(RuntimeError):
        controller.start()
    controller.stop()


def test_thread_controller_restart_after_interrupted_stop(monkeypatch):
    from logbook.queues import SubscriberGroup

    def interrupted_join():
        raise KeyboardInterrupt

    controller = SubscriberGroup().dispatch_in_background()
    with monkeypatch.context() as m:
        m.setattr(controller._thread, "join", interrupted_join)
        with pytest.raises(KeyboardInterrupt):
            controller.stop()
    controller.stop()
    controller.start()
    controller.stop()


def test_subscriber_group_stops_while_idle():
    from logbook.queues import MultiProcessingSubscriber, SubscriberGroup

    group = SubscriberGroup([MultiProcessingSubscriber()])
    stopper = threading.Thread(target=group.stop, daemon=True)
    stopper.start()
    stopper.join(2)
    assert not stopper.is_alive()


def test_message_queue_subscriber_recv_timeout():
    from logbook.queues import MessageQueueSubscriber

    subscriber = object.__new__(MessageQueueSubscriber)
    subscriber.queue = Queue()
    assert subscriber.recv(0.01) is None


@require_module("redis")
def test_redis_handler():
    import redis

    from logbook.queues import RedisHandler

    KEY = f"redis-{os.getpid()}"
    FIELDS = ["message", "host"]
    r = redis.Redis(REDIS_HOST, REDIS_PORT, decode_responses=True)
    redis_handler = RedisHandler(key=KEY, level=logbook.INFO, bubble=True)
    # We don't want output for the tests, so we can wrap everything in a
    # NullHandler
    null_handler = logbook.NullHandler()

    # Check default values
    with null_handler.applicationbound():
        with redis_handler:
            logbook.info(LETTERS)

    key, message = r.blpop(KEY)
    # Are all the fields in the record?
    for field in FIELDS:
        assert message.find(field)
    assert key == KEY
    assert message.find(LETTERS)
    assert json.loads(message)["channel"] == "Generic"

    # Change the key of the handler and check on redis
    KEY = f"test_another_key-{os.getpid()}"
    redis_handler.key = KEY

    with null_handler.applicationbound():
        with redis_handler:
            logbook.info(LETTERS)

    key, message = r.blpop(KEY)
    assert key == KEY

    # Check that extra fields are added if specified when creating the handler
    FIELDS.append("type")
    extra_fields = {"type": "test"}
    del redis_handler
    redis_handler = RedisHandler(
        key=KEY, level=logbook.INFO, extra_fields=extra_fields, bubble=True
    )

    with null_handler.applicationbound():
        with redis_handler:
            logbook.info(LETTERS)

    key, message = r.blpop(KEY)
    for field in FIELDS:
        assert message.find(field)
    assert message.find("test")

    # And finally, check that fields are correctly added if appended to the
    # log message
    FIELDS.append("more_info")
    with null_handler.applicationbound():
        with redis_handler:
            logbook.info(LETTERS, more_info="This works")

    key, message = r.blpop(KEY)
    for field in FIELDS:
        assert message.find(field)
    assert message.find("This works")


@require_module("redis")
def test_redis_handler_lpush():
    """
    Test if lpush stores messages in the right order
    new items should be first on list
    """
    import redis

    from logbook.queues import RedisHandler

    null_handler = logbook.NullHandler()

    KEY = "lpushed-"
    redis_handler = RedisHandler(
        key=KEY, push_method="lpush", level=logbook.INFO, bubble=True
    )

    with null_handler.applicationbound():
        with redis_handler:
            logbook.info("old item")
            logbook.info("new item")

    time.sleep(1.5)

    r = redis.Redis(REDIS_HOST, REDIS_PORT, decode_responses=True)
    logs = r.lrange(KEY, 0, -1)
    assert logs
    assert "new item" in logs[0]
    r.delete(KEY)


@require_module("redis")
def test_redis_handler_rpush():
    """
    Test if rpush stores messages in the right order
    old items should be first on list
    """
    import redis

    from logbook.queues import RedisHandler

    null_handler = logbook.NullHandler()

    KEY = "rpushed-" + str(os.getpid())
    redis_handler = RedisHandler(
        key=KEY, push_method="rpush", level=logbook.INFO, bubble=True
    )

    with null_handler.applicationbound():
        with redis_handler:
            logbook.info("old item")
            logbook.info("new item")

    time.sleep(1.5)

    r = redis.Redis(REDIS_HOST, REDIS_PORT, decode_responses=True)
    logs = r.lrange(KEY, 0, -1)
    assert logs
    assert "old item" in logs[0]
    r.delete(KEY)


def redis_record(message):
    record = logbook.LogRecord("redis", logbook.INFO, message)
    record.heavy_init()
    return record


def redis_messages(r, key):
    return [json.loads(value)["message"] for value in r.lrange(key, 0, -1)]


def wait_for_redis_messages(r, key, messages):
    deadline = time.monotonic() + 2
    while redis_messages(r, key) != messages and time.monotonic() < deadline:
        time.sleep(0.01)
    assert redis_messages(r, key) == messages


@require_module("redis")
def test_redis_handler_flushes_without_blocking_emit(monkeypatch):
    import redis

    from logbook.queues import RedisHandler

    KEY = f"redis-{os.getpid()}-flush"
    r = redis.Redis(REDIS_HOST, REDIS_PORT, decode_responses=True)
    r.delete(KEY)
    handler = RedisHandler(key=KEY, flush_threshold=1, flush_time=60)
    entered = threading.Event()
    release = threading.Event()
    rpush = handler.redis.rpush

    def blocking_rpush(*args):
        entered.set()
        assert release.wait(2)
        return rpush(*args)

    monkeypatch.setattr(handler.redis, "rpush", blocking_rpush)
    handler.emit(redis_record("a"))
    assert entered.wait(2)
    handler.emit(redis_record("b"))
    closer = threading.Thread(target=handler.close)
    closer.start()
    closer.join(0.1)
    assert closer.is_alive()
    release.set()
    closer.join(2)
    assert redis_messages(r, KEY) == ["a", "b"]
    assert not handler._flushing_t.is_alive()
    r.delete(KEY)


@require_module("redis")
def test_redis_handler_retries_failed_flush(monkeypatch, capsys):
    import redis

    from logbook.queues import RedisHandler

    KEY = f"redis-{os.getpid()}-retry"
    r = redis.Redis(REDIS_HOST, REDIS_PORT, decode_responses=True)
    r.delete(KEY)
    handler = RedisHandler(key=KEY, flush_time=0.01)
    failures = 2
    entered = threading.Event()
    release = threading.Event()
    rpush = handler.redis.rpush

    def failing_rpush(*args):
        nonlocal failures
        if failures:
            failures -= 1
            if not failures:
                entered.set()
                assert release.wait(2)
            raise redis.ConnectionError("Redis is down")
        return rpush(*args)

    monkeypatch.setattr(handler.redis, "rpush", failing_rpush)
    handler.emit(redis_record("a"))
    assert entered.wait(2)
    assert capsys.readouterr().err == ""
    handler.emit_batch([redis_record("b"), redis_record("c")], "group")
    err = capsys.readouterr().err
    assert err.count("ConnectionError: Redis is down") == 1
    assert f"Logged from file {os.path.abspath(__file__)}, line " in err
    release.set()
    wait_for_redis_messages(r, KEY, ["a", "b", "c"])
    handler.handle(redis_record("d"))
    assert capsys.readouterr().err == ""
    wait_for_redis_messages(r, KEY, ["a", "b", "c", "d"])
    failures = 1
    handler.emit(redis_record("e"))
    wait_for_redis_messages(r, KEY, ["a", "b", "c", "d", "e"])
    with logbook.Flags(errors="raise"), pytest.raises(redis.ConnectionError):
        handler.handle(redis_record("f"))
    handler.close()
    assert redis_messages(r, KEY) == ["a", "b", "c", "d", "e", "f"]
    assert capsys.readouterr().err == ""
    r.delete(KEY)


@require_module("redis")
def test_redis_handler_pushes_directly_when_not_buffering():
    import redis

    from logbook.queues import RedisHandler

    KEY = f"redis-{os.getpid()}-direct"
    r = redis.Redis(REDIS_HOST, REDIS_PORT, decode_responses=True)
    r.delete(KEY)
    handler = RedisHandler(key=KEY, flush_time=60)
    handler.emit(redis_record("a"))
    handler.disable_buffering()
    handler.emit(redis_record("b"))
    assert redis_messages(r, KEY) == ["a", "b"]
    handler.close()

    handler = RedisHandler(key=KEY, flush_time=60)
    handler.close()
    handler.emit(redis_record("c"))
    assert redis_messages(r, KEY) == ["a", "b", "c"]
    r.delete(KEY)


@require_module("redis")
@pytest.mark.skipif(not hasattr(os, "fork"), reason="requires os.fork")
@pytest.mark.filterwarnings("ignore:This process:DeprecationWarning")
def test_redis_handler_pushes_from_forked_child():
    import redis

    from logbook.queues import RedisHandler

    KEY = f"redis-{os.getpid()}-fork"
    r = redis.Redis(REDIS_HOST, REDIS_PORT, decode_responses=True)
    r.delete(KEY)
    handler = RedisHandler(key=KEY, flush_threshold=1, flush_time=60)

    def child():
        handler.emit(redis_record("a"))
        wait_for_redis_messages(r, KEY, ["a"])

    fork(child)
    handler.close()
    r.delete(KEY)


@require_module("redis")
@pytest.mark.skipif(not hasattr(os, "fork"), reason="requires os.fork")
@pytest.mark.filterwarnings("ignore:This process:DeprecationWarning")
def test_redis_handler_lock_held_by_another_thread_at_fork():
    import redis

    from logbook.queues import RedisHandler

    KEY = f"redis-{os.getpid()}-fork-lock"
    r = redis.Redis(REDIS_HOST, REDIS_PORT, decode_responses=True)
    r.delete(KEY)
    handler = RedisHandler(key=KEY, flush_threshold=1, flush_time=60)

    def child():
        handler.emit(redis_record("a"))
        wait_for_redis_messages(r, KEY, ["a"])

    fork_while_held(handler.lock, child)
    handler.close()
    r.delete(KEY)


@pytest.fixture
def handlers(handlers_subscriber):
    return handlers_subscriber[0]


@pytest.fixture
def subscriber(handlers_subscriber):
    return handlers_subscriber[1]


@pytest.fixture
def handlers_subscriber(multi):
    from logbook.queues import ZeroMQHandler, ZeroMQSubscriber

    host, unused_port = unused_tcp_address()

    # Retrieve the ZeroMQ handler and subscriber
    uri = "tcp://%s:%d" % (host, unused_port)  # noqa: UP031
    if multi:
        handlers = [ZeroMQHandler(uri, multi=True) for _ in range(3)]
    else:
        handlers = [ZeroMQHandler(uri)]
    subscriber = ZeroMQSubscriber(uri, multi=multi)
    # Enough time to start
    time.sleep(0.1)
    return handlers, subscriber


@pytest.fixture(params=[True, False], ids=["multi", "nomulti"])
def multi(request):
    return request.param
