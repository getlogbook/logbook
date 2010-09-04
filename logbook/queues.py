# -*- coding: utf-8 -*-
"""
    logbook.queues
    ~~~~~~~~~~~~~~

    This module implements queue backends.

    :copyright: (c) 2010 by Armin Ronacher, Georg Brandl.
    :license: BSD, see LICENSE for more details.
"""
from logbook.base import NOTSET
from logbook.handlers import Handler
from logbook.helpers import json


class ZeroMQHandler(Handler):
    """A handler that acts as a ZeroMQ publisher, which publishes each record
    as json dump.  Requires the pyzmq library.

    The queue will be filled with JSON exported log records.  Here an example
    of how to recieve the records::

        import zmq
        import json
        from logbook import LogRecord
        handler = logbook.more.ZeroMQHandler('tcp://127.0.0.1:5000')
        context = zmq.Context()
        socket = context.socket(zmq.SUB)
        socket.connect(uri)
        socket.setsockopt(zmq.SUBSCRIBE, '')
        while 1:
            record = LogRecord.from_dict(json.loads(socket.recv()))
    """

    def __init__(self, uri, level=NOTSET, filter=None, bubble=False):
        Handler.__init__(self, level, filter, bubble)

        try:
            import zmq
        except ImportError:
            raise RuntimeError('pyzmq has to be installed for this handler.')
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.PUB)
        self.socket.bind(uri)

    def export_record(self, record):
        """Exports the record into a dictionary ready for JSON dumping."""
        return record.to_dict(json_safe=True)

    def emit(self, record):
        self.socket.send(json.dumps(self.export_record(record)))

    def close(self):
        self.socket.close()
