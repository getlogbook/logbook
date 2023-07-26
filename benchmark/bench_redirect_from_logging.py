"""Tests redirects from logging to logbook"""
from io import StringIO
from logging import getLogger

from logbook import StreamHandler
from logbook.compat import redirect_logging

redirect_logging()
log = getLogger("Test logger")


def run():
    out = StringIO()
    with StreamHandler(out):
        for x in range(500):
            log.warning("this is not handled")
    assert out.getvalue().count("\n") == 500
