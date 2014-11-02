# -*- coding: utf-8 -*-
import time
import socket

from .utils import require_module, missing, LETTERS

import logbook
from logbook.helpers import u

import pytest


@require_module('zmq')
def test_zeromq_handler(logger, handlers, subscriber):
    tests = [
        u('Logging something'),
        u('Something with umlauts äöü'),
        u('Something else for good measure'),
    ]
    for test in tests:
        for handler in handlers:
            with handler:
                logger.warn(test)
                record = subscriber.recv()
                assert record.message == test
                assert record.channel == logger.name


@require_module('zmq')
def test_zeromq_background_thread(logger, handlers, subscriber):
    test_handler = logbook.TestHandler()
    controller = subscriber.dispatch_in_background(test_handler)

    for handler in handlers:
        with handler:
            logger.warn('This is a warning')
            logger.error('This is an error')

    # stop the controller.  This will also stop the loop and join the
    # background process.  Before that we give it a fraction of a second
    # to get all results
    time.sleep(0.5)
    controller.stop()

    assert test_handler.has_warning('This is a warning')
    assert test_handler.has_error('This is an error')


@missing('zmq')
def test_missing_zeromq():
    from logbook.queues import ZeroMQHandler, ZeroMQSubscriber
    with pytest.raises(RuntimeError):
        ZeroMQHandler('tcp://127.0.0.1:42000')
    with pytest.raises(RuntimeError):
        ZeroMQSubscriber('tcp://127.0.0.1:42000')


class MultiProcessingHandlerSendBack(object):
    def __init__(self, queue):
        self.queue = queue

    def __call__(self):
        from logbook.queues import MultiProcessingHandler
        handler = MultiProcessingHandler(self.queue)
        handler.push_thread()
        try:
            logbook.warn('Hello World')
        finally:
            handler.pop_thread()


@require_module('multiprocessing')
def test_multi_processing_handler():
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
        assert test_handler.has_warning('Hello World')


def test_threaded_wrapper_handler(logger):
    from logbook.queues import ThreadedWrapperHandler
    test_handler = logbook.TestHandler()
    with ThreadedWrapperHandler(test_handler) as handler:
        logger.warn('Just testing')
        logger.error('More testing')

    # give it some time to sync up
    handler.close()

    assert (not handler.controller.running)
    assert test_handler.has_warning('Just testing')
    assert test_handler.has_error('More testing')


@require_module('execnet')
def test_execnet_handler():
    def run_on_remote(channel):
        import logbook
        from logbook.queues import ExecnetChannelHandler
        handler = ExecnetChannelHandler(channel)
        log = logbook.Logger('Execnet')
        handler.push_application()
        log.info('Execnet works')

    import execnet
    gw = execnet.makegateway()
    channel = gw.remote_exec(run_on_remote)
    from logbook.queues import ExecnetChannelSubscriber
    subscriber = ExecnetChannelSubscriber(channel)
    record = subscriber.recv()
    assert record.msg == 'Execnet works'
    gw.exit()


class SubscriberGroupSendBack(object):
    def __init__(self, message, queue):
        self.message = message
        self.queue = queue

    def __call__(self):
        from logbook.queues import MultiProcessingHandler
        with MultiProcessingHandler(self.queue):
            logbook.warn(self.message)


@require_module('multiprocessing')
def test_subscriber_group():
    from multiprocessing import Process, Queue
    from logbook.queues import MultiProcessingSubscriber, SubscriberGroup
    a_queue = Queue(-1)
    b_queue = Queue(-1)
    subscriber = SubscriberGroup([
        MultiProcessingSubscriber(a_queue),
        MultiProcessingSubscriber(b_queue)
    ])

    for _ in range(10):
        p1 = Process(target=SubscriberGroupSendBack('foo', a_queue))
        p2 = Process(target=SubscriberGroupSendBack('bar', b_queue))
        p1.start()
        p2.start()
        p1.join()
        p2.join()
        messages = [subscriber.recv().message for i in (1, 2)]
        assert sorted(messages) == ['bar', 'foo']


@require_module('redis')
def test_redis_handler():
    import redis
    from logbook.queues import RedisHandler

    KEY = 'redis'
    FIELDS = ['message', 'host']
    r = redis.Redis(decode_responses=True)
    redis_handler = RedisHandler(level=logbook.INFO, bubble=True)
    # We don't want output for the tests, so we can wrap everything in a NullHandler
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

    # Change the key of the handler and check on redis
    KEY = 'test_another_key'
    redis_handler.key = KEY

    with null_handler.applicationbound():
        with redis_handler:
            logbook.info(LETTERS)

    key, message = r.blpop(KEY)
    assert key == KEY

    # Check that extra fields are added if specified when creating the handler
    FIELDS.append('type')
    extra_fields = {'type': 'test'}
    del(redis_handler)
    redis_handler = RedisHandler(key=KEY, level=logbook.INFO,
                                 extra_fields=extra_fields, bubble=True)

    with null_handler.applicationbound():
        with redis_handler:
            logbook.info(LETTERS)

    key, message = r.blpop(KEY)
    for field in FIELDS:
        assert message.find(field)
    assert message.find('test')

    # And finally, check that fields are correctly added if appended to the
    # log message
    FIELDS.append('more_info')
    with null_handler.applicationbound():
        with redis_handler:
            logbook.info(LETTERS, more_info='This works')

    key, message = r.blpop(KEY)
    for field in FIELDS:
        assert message.find(field)
    assert message.find('This works')


@require_module('redis')
def test_redis_handler_lpush():
    """
    Test if lpush stores messages in the right order
    new items should be first on list
    """
    import redis
    from logbook.queues import RedisHandler
    null_handler = logbook.NullHandler()

    redis_handler = RedisHandler(key='lpushed', push_method='lpush',
                                 level=logbook.INFO, bubble=True)

    with null_handler.applicationbound():
        with redis_handler:
            logbook.info("old item")
            logbook.info("new item")

    time.sleep(1.5)

    r = redis.Redis(decode_responses=True)
    logs = r.lrange('lpushed', 0, -1)
    assert logs
    assert "new item" in logs[0]
    r.delete('lpushed')


@require_module('redis')
def test_redis_handler_rpush():
    """
    Test if rpush stores messages in the right order
    old items should be first on list
    """
    import redis
    from logbook.queues import RedisHandler
    null_handler = logbook.NullHandler()

    redis_handler = RedisHandler(key='rpushed', push_method='rpush',
                                 level=logbook.INFO, bubble=True)

    with null_handler.applicationbound():
        with redis_handler:
            logbook.info("old item")
            logbook.info("new item")

    time.sleep(1.5)

    r = redis.Redis(decode_responses=True)
    logs = r.lrange('rpushed', 0, -1)
    assert logs
    assert "old item" in logs[0]
    r.delete('rpushed')


@pytest.fixture
def handlers(handlers_subscriber):
    return handlers_subscriber[0]


@pytest.fixture
def subscriber(handlers_subscriber):
    return handlers_subscriber[1]


@pytest.fixture
def handlers_subscriber(multi):
    from logbook.queues import ZeroMQHandler, ZeroMQSubscriber

    # Get an unused port
    tempsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tempsock.bind(('127.0.0.1', 0))
    host, unused_port = tempsock.getsockname()
    tempsock.close()

    # Retrieve the ZeroMQ handler and subscriber
    uri = 'tcp://%s:%d' % (host, unused_port)
    if multi:
        handlers = [ZeroMQHandler(uri, multi=True) for _ in range(3)]
    else:
        handlers = [ZeroMQHandler(uri)]
    subscriber = ZeroMQSubscriber(uri, multi=multi)
    # Enough time to start
    time.sleep(0.1)
    return handlers, subscriber


@pytest.fixture(params=[True, False])
def multi(request):
    return request.param
