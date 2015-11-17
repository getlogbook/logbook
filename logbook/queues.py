# -*- coding: utf-8 -*-
"""
    logbook.queues
    ~~~~~~~~~~~~~~

    This module implements queue backends.

    :copyright: (c) 2010 by Armin Ronacher, Georg Brandl.
    :license: BSD, see LICENSE for more details.
"""
import json
import threading
from threading import Thread, Lock
import platform
from logbook.base import NOTSET, LogRecord, dispatch_record
from logbook.handlers import Handler, WrapperHandler
from logbook.helpers import PY2, u

if PY2:
    from Queue import Empty, Full, Queue as ThreadQueue
else:
    from queue import Empty, Full, Queue as ThreadQueue


class RedisHandler(Handler):
    """A handler that sends log messages to a Redis instance.

    It publishes each record as json dump. Requires redis module.

    To receive such records you need to have a running instance of Redis.

    Example setup::

        handler = RedisHandler('http://127.0.0.1', port='9200', key='redis')

    If your Redis instance is password protected, you can securely connect
    passing your password when creating a RedisHandler object.

    Example::

        handler = RedisHandler(password='your_redis_password')

    More info about the default buffer size: wp.me/p3tYJu-3b
    """
    def __init__(self, host='127.0.0.1', port=6379, key='redis',
                 extra_fields={}, flush_threshold=128, flush_time=1,
                 level=NOTSET, filter=None, password=False, bubble=True,
                 context=None, push_method='rpush'):
        Handler.__init__(self, level, filter, bubble)
        try:
            import redis
            from redis import ResponseError
        except ImportError:
            raise RuntimeError('The redis library is required for '
                               'the RedisHandler')

        self.redis = redis.Redis(host=host, port=port, password=password,
                                 decode_responses=True)
        try:
            self.redis.ping()
        except ResponseError:
            raise ResponseError(
                'The password provided is apparently incorrect')
        self.key = key
        self.extra_fields = extra_fields
        self.flush_threshold = flush_threshold
        self.queue = []
        self.lock = Lock()
        self.push_method = push_method

        # Set up a thread that flushes the queue every specified seconds
        self._stop_event = threading.Event()
        self._flushing_t = threading.Thread(target=self._flush_task,
                                            args=(flush_time,
                                                  self._stop_event))
        self._flushing_t.daemon = True
        self._flushing_t.start()

    def _flush_task(self, time, stop_event):
        """Calls the method _flush_buffer every certain time.
        """
        while not self._stop_event.isSet():
            with self.lock:
                self._flush_buffer()
            self._stop_event.wait(time)

    def _flush_buffer(self):
        """Flushes the messaging queue into Redis.

        All values are pushed at once for the same key.

        The method rpush/lpush is defined by push_method argument
        """
        if self.queue:
            getattr(self.redis, self.push_method)(self.key, *self.queue)
        self.queue = []

    def disable_buffering(self):
        """Disables buffering.

        If called, every single message will be directly pushed to Redis.
        """
        self._stop_event.set()
        self.flush_threshold = 1

    def emit(self, record):
        """Emits a pair (key, value) to redis.

        The key is the one provided when creating the handler, or redis if none
        was provided. The value contains both the message and the hostname.
        Extra values are also appended to the message.
        """
        with self.lock:
            r = {"message": record.msg,
                 "host": platform.node(),
                 "level": record.level_name,
                 "time": record.time.isoformat()}
            r.update(self.extra_fields)
            r.update(record.kwargs)
            self.queue.append(json.dumps(r))
            if len(self.queue) == self.flush_threshold:
                self._flush_buffer()

    def close(self):
        self._flush_buffer()


class MessageQueueHandler(Handler):
    """A handler that acts as a message queue publisher, which publishes each
    record as json dump. Requires the kombu module.

    The queue will be filled with JSON exported log records.  To receive such
    log records from a queue you can use the :class:`MessageQueueSubscriber`.

    For an AMQP backend such as RabbitMQ::

        handler = MessageQueueHandler('amqp://guest:guest@localhost//')

    This requires the py-amqp or the librabbitmq client library.

    For Redis (requires redis client library)::

        handler = MessageQueueHandler('redis://localhost:8889/0')

    For MongoDB (requires pymongo)::

        handler = MessageQueueHandler('mongodb://localhost:27017/logging')

    Several other backends are also supported.
    Refer to the `kombu`_ documentation

    .. _kombu: http://kombu.readthedocs.org/en/latest/introduction.html
    """

    def __init__(self, uri=None, queue='logging', level=NOTSET,
                 filter=None, bubble=False):
        Handler.__init__(self, level, filter, bubble)
        try:
            import kombu
        except ImportError:
            raise RuntimeError('The kombu library is required for '
                               'the RabbitMQSubscriber.')
        if uri:
            connection = kombu.Connection(uri)

        self.queue = connection.SimpleQueue(queue)

    def export_record(self, record):
        """Exports the record into a dictionary ready for JSON dumping.
        """
        return record.to_dict(json_safe=True)

    def emit(self, record):
        self.queue.put(self.export_record(record))

    def close(self):
        self.queue.close()


RabbitMQHandler = MessageQueueHandler


class ZeroMQHandler(Handler):
    """A handler that acts as a ZeroMQ publisher, which publishes each record
    as json dump.  Requires the pyzmq library.

    The queue will be filled with JSON exported log records.  To receive such
    log records from a queue you can use the :class:`ZeroMQSubscriber`.

    If `multi` is set to `True`, the handler will use a `PUSH` socket to
    publish the records. This allows multiple handlers to use the same `uri`.
    The records can be received by using the :class:`ZeroMQSubscriber` with
    `multi` set to `True`.


    Example setup::

        handler = ZeroMQHandler('tcp://127.0.0.1:5000')
    """

    def __init__(self, uri=None, level=NOTSET, filter=None, bubble=False,
                 context=None, multi=False):
        Handler.__init__(self, level, filter, bubble)
        try:
            import zmq
        except ImportError:
            raise RuntimeError('The pyzmq library is required for '
                               'the ZeroMQHandler.')
        #: the zero mq context
        self.context = context or zmq.Context()

        if multi:
            #: the zero mq socket.
            self.socket = self.context.socket(zmq.PUSH)
            if uri is not None:
                self.socket.connect(uri)
        else:
            #: the zero mq socket.
            self.socket = self.context.socket(zmq.PUB)
            if uri is not None:
                self.socket.bind(uri)

    def export_record(self, record):
        """Exports the record into a dictionary ready for JSON dumping."""
        return record.to_dict(json_safe=True)

    def emit(self, record):
        self.socket.send(json.dumps(
            self.export_record(record)).encode("utf-8"))

    def close(self, linger=-1):
        self.socket.close(linger)

    def __del__(self):
        # When the Handler is deleted we must close our socket in a
        # non-blocking fashion (using linger).
        # Otherwise it can block indefinitely, for example if the Subscriber is
        # not reachable.
        # If messages are pending on the socket, we wait 100ms for them to be
        # sent then we discard them.
        self.close(linger=100)


class ThreadController(object):
    """A helper class used by queue subscribers to control the background
    thread.  This is usually created and started in one go by
    :meth:`~logbook.queues.ZeroMQSubscriber.dispatch_in_background` or
    a comparable function.
    """

    def __init__(self, subscriber, setup=None):
        self.setup = setup
        self.subscriber = subscriber
        self.running = False
        self._thread = None

    def start(self):
        """Starts the task thread."""
        self.running = True
        self._thread = Thread(target=self._target)
        self._thread.setDaemon(True)
        self._thread.start()

    def stop(self):
        """Stops the task thread."""
        if self.running:
            self.running = False
            self._thread.join()
            self._thread = None

    def _target(self):
        if self.setup is not None:
            self.setup.push_thread()
        try:
            while self.running:
                self.subscriber.dispatch_once(timeout=0.05)
        finally:
            if self.setup is not None:
                self.setup.pop_thread()


class SubscriberBase(object):
    """Baseclass for all subscribers."""

    def recv(self, timeout=None):
        """Receives a single record from the socket.  Timeout of 0 means
        nonblocking, `None` means blocking and otherwise it's a timeout in
        seconds after which the function just returns with `None`.

        Subclasses have to override this.
        """
        raise NotImplementedError()

    def dispatch_once(self, timeout=None):
        """Receives one record from the socket, loads it and dispatches it.  Returns
        `True` if something was dispatched or `False` if it timed out.
        """
        rv = self.recv(timeout)
        if rv is not None:
            dispatch_record(rv)
            return True
        return False

    def dispatch_forever(self):
        """Starts a loop that dispatches log records forever."""
        while 1:
            self.dispatch_once()

    def dispatch_in_background(self, setup=None):
        """Starts a new daemonized thread that dispatches in the background.
        An optional handler setup can be provided that pushed to the new
        thread (can be any :class:`logbook.base.StackedObject`).

        Returns a :class:`ThreadController` object for shutting down
        the background thread.  The background thread will already be
        running when this function returns.
        """
        controller = ThreadController(self, setup)
        controller.start()
        return controller


class MessageQueueSubscriber(SubscriberBase):
    """A helper that acts as a message queue subscriber and will dispatch
    received log records to the active handler setup. There are multiple ways
    to use this class.

    It can be used to receive log records from a queue::

        subscriber = MessageQueueSubscriber('mongodb://localhost:27017/logging')
        record = subscriber.recv()

    But it can also be used to receive and dispatch these in one go::

        with target_handler:
            subscriber = MessageQueueSubscriber('mongodb://localhost:27017/logging')
            subscriber.dispatch_forever()

    This will take all the log records from that queue and dispatch them
    over to `target_handler`.  If you want you can also do that in the
    background::

        subscriber = MessageQueueSubscriber('mongodb://localhost:27017/logging')
        controller = subscriber.dispatch_in_background(target_handler)

    The controller returned can be used to shut down the background
    thread::

        controller.stop()
    """
    def __init__(self, uri=None, queue='logging'):
        try:
            import kombu
        except ImportError:
            raise RuntimeError('The kombu library is required.')
        if uri:
            connection = kombu.Connection(uri)

        self.queue = connection.SimpleQueue(queue)

    def __del__(self):
        try:
            self.close()
        except AttributeError:
            # subscriber partially created
            pass

    def close(self):
        self.queue.close()

    def recv(self, timeout=None):
        """Receives a single record from the socket.  Timeout of 0 means
        nonblocking, `None` means blocking and otherwise it's a timeout in
        seconds after which the function just returns with `None`.
        """
        if timeout == 0:
            try:
                rv = self.queue.get(block=False)
            except Exception:
                return
        else:
            rv = self.queue.get(timeout=timeout)

        log_record = rv.payload
        rv.ack()

        return LogRecord.from_dict(log_record)


RabbitMQSubscriber = MessageQueueSubscriber


class ZeroMQSubscriber(SubscriberBase):
    """A helper that acts as ZeroMQ subscriber and will dispatch received
    log records to the active handler setup.  There are multiple ways to
    use this class.

    It can be used to receive log records from a queue::

        subscriber = ZeroMQSubscriber('tcp://127.0.0.1:5000')
        record = subscriber.recv()

    But it can also be used to receive and dispatch these in one go::

        with target_handler:
            subscriber = ZeroMQSubscriber('tcp://127.0.0.1:5000')
            subscriber.dispatch_forever()

    This will take all the log records from that queue and dispatch them
    over to `target_handler`.  If you want you can also do that in the
    background::

        subscriber = ZeroMQSubscriber('tcp://127.0.0.1:5000')
        controller = subscriber.dispatch_in_background(target_handler)

    The controller returned can be used to shut down the background
    thread::

        controller.stop()

    If `multi` is set to `True`, the subscriber will use a `PULL` socket
    and listen to records published by a `PUSH` socket (usually via a
    :class:`ZeroMQHandler` with `multi` set to `True`). This allows a
    single subscriber to dispatch multiple handlers.
    """

    def __init__(self, uri=None, context=None, multi=False):
        try:
            import zmq
        except ImportError:
            raise RuntimeError('The pyzmq library is required for '
                               'the ZeroMQSubscriber.')
        self._zmq = zmq

        #: the zero mq context
        self.context = context or zmq.Context()

        if multi:
            #: the zero mq socket.
            self.socket = self.context.socket(zmq.PULL)
            if uri is not None:
                self.socket.bind(uri)
        else:
            #: the zero mq socket.
            self.socket = self.context.socket(zmq.SUB)
            if uri is not None:
                self.socket.connect(uri)
            self.socket.setsockopt_unicode(zmq.SUBSCRIBE, u(''))

    def __del__(self):
        try:
            self.close()
        except AttributeError:
            # subscriber partially created
            pass

    def close(self):
        """Closes the zero mq socket."""
        self.socket.close()

    def recv(self, timeout=None):
        """Receives a single record from the socket.  Timeout of 0 means
        nonblocking, `None` means blocking and otherwise it's a timeout in
        seconds after which the function just returns with `None`.
        """
        if timeout is None:
            rv = self.socket.recv()
        elif not timeout:
            rv = self.socket.recv(self._zmq.NOBLOCK)
            if rv is None:
                return
        else:
            if not self._zmq.select([self.socket], [], [], timeout)[0]:
                return
            rv = self.socket.recv(self._zmq.NOBLOCK)
        if not PY2:
            rv = rv.decode("utf-8")
        return LogRecord.from_dict(json.loads(rv))


def _fix_261_mplog():
    """necessary for older python's to disable a broken monkeypatch
    in the logging module.  See multiprocessing/util.py for the
    hasattr() check.  At least in Python 2.6.1 the multiprocessing
    module is not imported by logging and as such the test in
    the util fails.
    """
    import logging
    import multiprocessing
    logging.multiprocessing = multiprocessing


class MultiProcessingHandler(Handler):
    """Implements a handler that dispatches over a queue to a different
    process.  It is connected to a subscriber with a
    :class:`multiprocessing.Queue`::

        from multiprocessing import Queue
        from logbook.queues import MultiProcessingHandler
        queue = Queue(-1)
        handler = MultiProcessingHandler(queue)

    """

    def __init__(self, queue, level=NOTSET, filter=None, bubble=False):
        Handler.__init__(self, level, filter, bubble)
        self.queue = queue
        _fix_261_mplog()

    def emit(self, record):
        self.queue.put_nowait(record.to_dict(json_safe=True))


class MultiProcessingSubscriber(SubscriberBase):
    """Receives log records from the given multiprocessing queue and
    dispatches them to the active handler setup.  Make sure to use the same
    queue for both handler and subscriber.  Idaelly the queue is set
    up with maximum size (``-1``)::

        from multiprocessing import Queue
        queue = Queue(-1)

    It can be used to receive log records from a queue::

        subscriber = MultiProcessingSubscriber(queue)
        record = subscriber.recv()

    But it can also be used to receive and dispatch these in one go::

        with target_handler:
            subscriber = MultiProcessingSubscriber(queue)
            subscriber.dispatch_forever()

    This will take all the log records from that queue and dispatch them
    over to `target_handler`.  If you want you can also do that in the
    background::

        subscriber = MultiProcessingSubscriber(queue)
        controller = subscriber.dispatch_in_background(target_handler)

    The controller returned can be used to shut down the background
    thread::

        controller.stop()

    If no queue is provided the subscriber will create one.  This one can the
    be used by handlers::

        subscriber = MultiProcessingSubscriber()
        handler = MultiProcessingHandler(subscriber.queue)
    """

    def __init__(self, queue=None):
        if queue is None:
            from multiprocessing import Queue
            queue = Queue(-1)
        self.queue = queue
        _fix_261_mplog()

    def recv(self, timeout=None):
        if timeout is None:
            rv = self.queue.get()
        else:
            try:
                rv = self.queue.get(block=False, timeout=timeout)
            except Empty:
                return None
        return LogRecord.from_dict(rv)


class ExecnetChannelHandler(Handler):
    """Implements a handler that dispatches over a execnet channel
    to a different process.
    """

    def __init__(self, channel, level=NOTSET, filter=None, bubble=False):
        Handler.__init__(self, level, filter, bubble)
        self.channel = channel

    def emit(self, record):
        self.channel.send(record.to_dict(json_safe=True))


class ExecnetChannelSubscriber(SubscriberBase):
    """subscribes to a execnet channel"""

    def __init__(self, channel):
        self.channel = channel

    def recv(self, timeout=None):
        try:
            rv = self.channel.receive(timeout=timeout)
        except self.channel.RemoteError:
            # XXX: handle
            return None
        except (self.channel.TimeoutError, EOFError):
            return None
        else:
            return LogRecord.from_dict(rv)


class TWHThreadController(object):
    """A very basic thread controller that pulls things in from a
    queue and sends it to a handler.  Both queue and handler are
    taken from the passed :class:`ThreadedWrapperHandler`.
    """
    _sentinel = object()

    def __init__(self, wrapper_handler):
        self.wrapper_handler = wrapper_handler
        self.running = False
        self._thread = None

    def start(self):
        """Starts the task thread."""
        self.running = True
        self._thread = Thread(target=self._target)
        self._thread.setDaemon(True)
        self._thread.start()

    def stop(self):
        """Stops the task thread."""
        if self.running:
            self.wrapper_handler.queue.put_nowait(self._sentinel)
            self._thread.join()
            self._thread = None

    def _target(self):
        while 1:
            record = self.wrapper_handler.queue.get()
            if record is self._sentinel:
                self.running = False
                break
            self.wrapper_handler.handler.handle(record)


class ThreadedWrapperHandler(WrapperHandler):
    """This handled uses a single background thread to dispatch log records
    to a specific other handler using an internal queue.  The idea is that if
    you are using a handler that requires some time to hand off the log records
    (such as the mail handler) and would block your request, you can let
    Logbook do that in a background thread.

    The threaded wrapper handler will automatically adopt the methods and
    properties of the wrapped handler.  All the values will be reflected:

    >>> twh = ThreadedWrapperHandler(TestHandler())
    >>> from logbook import WARNING
    >>> twh.level_name = 'WARNING'
    >>> twh.handler.level_name
    'WARNING'
    """
    _direct_attrs = frozenset(['handler', 'queue', 'controller'])

    def __init__(self, handler, maxsize=0):
        WrapperHandler.__init__(self, handler)
        self.queue = ThreadQueue(maxsize)
        self.controller = TWHThreadController(self)
        self.controller.start()

    def close(self):
        self.controller.stop()
        self.handler.close()

    def emit(self, record):
        try:
            self.queue.put_nowait(record)
        except Full:
            # silently drop
            pass


class GroupMember(ThreadController):
    def __init__(self, subscriber, queue):
        ThreadController.__init__(self, subscriber, None)
        self.queue = queue

    def _target(self):
        if self.setup is not None:
            self.setup.push_thread()
        try:
            while self.running:
                record = self.subscriber.recv()
                if record:
                    try:
                        self.queue.put(record, timeout=0.05)
                    except Full:
                        pass
        finally:
            if self.setup is not None:
                self.setup.pop_thread()


class SubscriberGroup(SubscriberBase):
    """This is a subscriber which represents a group of subscribers.

    This is helpful if you are writing a server-like application which has
    "slaves". This way a user is easily able to view every log record which
    happened somewhere in the entire system without having to check every
    single slave::

        subscribers = SubscriberGroup([
            MultiProcessingSubscriber(queue),
            ZeroMQSubscriber('tcp://127.0.0.1:5000')
        ])
        with target_handler:
            subscribers.dispatch_forever()
    """
    def __init__(self, subscribers=None, queue_limit=10):
        self.members = []
        self.queue = ThreadQueue(queue_limit)
        for subscriber in subscribers or []:
            self.add(subscriber)

    def add(self, subscriber):
        """Adds the given `subscriber` to the group."""
        member = GroupMember(subscriber, self.queue)
        member.start()
        self.members.append(member)

    def recv(self, timeout=None):
        try:
            return self.queue.get(timeout=timeout)
        except Empty:
            return

    def stop(self):
        """Stops the group from internally recieving any more messages, once the
        internal queue is exhausted :meth:`recv` will always return `None`.
        """
        for member in self.members:
            self.member.stop()
