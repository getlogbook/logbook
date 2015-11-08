"""Tests basic stack manipulation performance"""
from logbook import Handler, NullHandler, StreamHandler, FileHandler, \
    ERROR, WARNING
from tempfile import NamedTemporaryFile
from cStringIO import StringIO


def run():
    f = NamedTemporaryFile()
    out = StringIO()
    with NullHandler():
        with StreamHandler(out, level=WARNING):
            with FileHandler(f.name, level=ERROR):
                for x in xrange(100):
                    list(Handler.stack_manager.iter_context_objects())
