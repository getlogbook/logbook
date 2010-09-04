# -*- coding: utf-8 -*-
"""
    logbook.queues
    ~~~~~~~~~~~~~~

    This module implements queue backends.

    :copyright: (c) 2010 by Armin Ronacher, Georg Brandl.
    :license: BSD, see LICENSE for more details.
"""
from threading import Thread
from logbook.base import NOTSET, LogRecord, dispatch_record
from logbook.handlers import Handler
from logbook.helpers import json


class ZeroMQHandler(Handler):
    """A handler that acts as a ZeroMQ publisher, which publishes each record
    as json dump.  Requires the pyzmq library.

    The queue will be filled with JSON exported log records.  To receive such
    log records from a queue you can use the :class:`ZeroMQSubscriber`.
    """

    def __init__(self, uri, level=NOTSET, filter=None, bubble=False):
        Handler.__init__(self, level, filter, bubble)
        try:
            import zmq
        except ImportError:
            raise RuntimeError('pyzmq has to be installed for this handler.')
        #: the zero mq context
        self.context = zmq.Context()
        #: the zero mq socket.
        self.socket = self.context.socket(zmq.PUB)
        self.socket.bind(uri)

    def export_record(self, record):
        """Exports the record into a dictionary ready for JSON dumping."""
        return record.to_dict(json_safe=True)

    def emit(self, record):
        self.socket.send(json.dumps(self.export_record(record)))

    def close(self):
        self.socket.close()


class ZeroMQThreadController(object):
    """A helper class used by :class:`ZeroMQSubscriber` to control
    the background thread.  This is usually created and started in
    one go by :meth:`~logbook.queues.ZeroMQSubscriber.dispatch_in_background`.
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
            self.subscriber.dispatch_forever()
        finally:
            if self.setup is not None:
                self.setup.pop_thread()


class ZeroMQSubscriber(object):
    """A helper that acts as ZeroMQ subscriber and will dispatch received
    log records to the active handler setup.
    """

    def __init__(self, uri):
        try:
            import zmq
        except ImportError:
            raise RuntimeError('pyzmq has to be installed for this handler.')
        self._zmq = zmq

        #: the zero mq context
        self.context = zmq.Context()
        #: the zero mq socket.
        self.socket = self.context.socket(zmq.SUB)
        self.socket.connect(uri)
        self.socket.setsockopt(zmq.SUBSCRIBE, '')

    def __del__(self):
        self.close()

    def close(self):
        """Closes the zero mq socket."""
        self.socket.close()

    def recv(self):
        """Receives a single record from the socket."""
        return LogRecord.from_dict(json.loads(self.socket.recv()))

    def dispatch_once(self):
        """Receives one record from the socket, loads it and dispatches it."""
        dispatch_record(self.recv())

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
        controller = ZeroMQThreadController(self, setup)
        controller.start()
        return controller
