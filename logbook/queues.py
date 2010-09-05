# -*- coding: utf-8 -*-
"""
    logbook.queues
    ~~~~~~~~~~~~~~

    This module implements queue backends.

    :copyright: (c) 2010 by Armin Ronacher, Georg Brandl.
    :license: BSD, see LICENSE for more details.
"""
from threading import Thread
from multiprocessing import Queue
from Queue import Empty
from logbook.base import NOTSET, LogRecord, dispatch_record
from logbook.handlers import Handler
from logbook.helpers import json


class ZeroMQHandler(Handler):
    """A handler that acts as a ZeroMQ publisher, which publishes each record
    as json dump.  Requires the pyzmq library.

    The queue will be filled with JSON exported log records.  To receive such
    log records from a queue you can use the :class:`ZeroMQSubscriber`.
    """

    def __init__(self, uri=None, level=NOTSET, filter=None, bubble=False):
        Handler.__init__(self, level, filter, bubble)
        try:
            import zmq
        except ImportError:
            raise RuntimeError('The pyzmq library is required for '
                               'the ZeroMQHandler.')
        #: the zero mq context
        self.context = zmq.Context()
        #: the zero mq socket.
        self.socket = self.context.socket(zmq.PUB)
        if uri is not None:
            self.socket.bind(uri)

    def export_record(self, record):
        """Exports the record into a dictionary ready for JSON dumping."""
        return record.to_dict(json_safe=True)

    def emit(self, record):
        self.socket.send(json.dumps(self.export_record(record)))

    def close(self):
        self.socket.close()


class ThreadController(object):
    """A helper class used by queue subscreibers to control the background
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
        """Receives a single record from the socket.  Timeout of 0 means nonblocking,
        `None` means blocking and otherwise it's a timeout in seconds after which
        the function just returns with `None`.

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

        Returns a :class:`ZeroMQThreadController` object for shutting down
        the background thread.  The background thread will already be
        running when this function returns.
        """
        controller = ThreadController(self, setup)
        controller.start()
        return controller


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
    """

    def __init__(self, uri=None):
        try:
            import zmq
        except ImportError:
            raise RuntimeError('The pyzmq library is required for '
                               'the ZeroMQSubscriber.')
        self._zmq = zmq

        #: the zero mq context
        self.context = zmq.Context()
        #: the zero mq socket.
        self.socket = self.context.socket(zmq.SUB)
        if uri is not None:
            self.socket.connect(uri)
        self.socket.setsockopt(zmq.SUBSCRIBE, '')

    def __del__(self):
        self.close()

    def close(self):
        """Closes the zero mq socket."""
        self.socket.close()

    def recv(self, timeout=None):
        """Receives a single record from the socket.  Timeout of 0 means nonblocking,
        `None` means blocking and otherwise it's a timeout in seconds after which
        the function just returns with `None`.
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
        return LogRecord.from_dict(json.loads(rv))


def _fix_261_mplog():
    """necessary for older python's to disable a broken monkeypatch
    in the logging module.  See multiprocessing/util.py for the
    hasattr() check.  At least in Python 2.6.1 the multiprocessing
    module is not imported by logging and as such the test in
    the util fails.
    """
    import logging, multiprocessing
    logging.multiprocessing = multiprocessing


class MultiProcessingHandler(Handler):
    """Implements a handler that dispatches over a queue to a different
    process.
    """

    # XXX: this should use a smilar interface to the ZeroMQ subscriber
    # which breaks up sender and receiver into two parts and provides an
    # interface to shut down the subscriber thread.  Additionally and
    # more importantly it does not deliver to a handler but dispatches
    # to a setup which is more useful

    def __init__(self, queue, level=NOTSET, filter=None, bubble=False):
        Handler.__init__(self, level, filter, bubble)
        self.queue = queue
        _fix_261_mplog()

    def emit(self, record):
        self.queue.put_nowait(record.to_dict(json_safe=True))


class MultiProcessingSubscriber(SubscriberBase):
    """Receives log records from the given multiprocessing queue and
    dispatches them to the active handler setup.
    """

    def __init__(self, queue):
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
