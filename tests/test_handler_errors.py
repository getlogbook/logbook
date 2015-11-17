import re
import sys

import logbook

import pytest

from .utils import capturing_stderr_context

__file_without_pyc__ = __file__
if __file_without_pyc__.endswith('.pyc'):
    __file_without_pyc__ = __file_without_pyc__[:-1]


def test_handler_exception(activation_strategy, logger):
    class ErroringHandler(logbook.TestHandler):

        def emit(self, record):
            raise RuntimeError('something bad happened')

    with capturing_stderr_context() as stderr:
        with activation_strategy(ErroringHandler()):
            logger.warn('I warn you.')
    assert 'something bad happened' in stderr.getvalue()
    assert 'I warn you' not in stderr.getvalue()


def test_formatting_exception():
    def make_record():
        return logbook.LogRecord('Test Logger', logbook.WARNING,
                                 'Hello {foo:invalid}',
                                 kwargs={'foo': 42},
                                 frame=sys._getframe())
    record = make_record()
    with pytest.raises(TypeError) as caught:
        record.message

    errormsg = str(caught.value)
    assert re.search(
        'Could not format message with provided arguments: Invalid '
        '(?:format specifier)|(?:conversion specification)|(?:format spec)',
        errormsg, re.M | re.S)
    assert "msg='Hello {foo:invalid}'" in errormsg
    assert 'args=()' in errormsg
    assert "kwargs={'foo': 42}" in errormsg
    assert re.search(
        r'Happened in file .*%s, line \d+' % re.escape(__file_without_pyc__),
        errormsg, re.M | re.S)
