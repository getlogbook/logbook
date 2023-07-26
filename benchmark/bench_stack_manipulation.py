"""Tests basic stack manipulation performance"""
from io import StringIO
from tempfile import NamedTemporaryFile

from logbook import ERROR, WARNING, FileHandler, Handler, NullHandler, StreamHandler


def run():
    f = NamedTemporaryFile()
    out = StringIO()
    with NullHandler():
        with StreamHandler(out, level=WARNING):
            with FileHandler(f.name, level=ERROR):
                for x in range(100):
                    list(Handler.stack_manager.iter_context_objects())
