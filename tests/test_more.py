import sys

import logbook
from logbook.helpers import StringIO

import pytest

from .utils import capturing_stderr_context, missing, require_module


@require_module('jinja2')
def test_jinja_formatter(logger):
    from logbook.more import JinjaFormatter
    fmter = JinjaFormatter('{{ record.channel }}/{{ record.level_name }}')
    handler = logbook.TestHandler()
    handler.formatter = fmter
    with handler:
        logger.info('info')
    assert 'testlogger/INFO' in handler.formatted_records


@missing('jinja2')
def test_missing_jinja2():
    from logbook.more import JinjaFormatter
    # check the RuntimeError is raised
    with pytest.raises(RuntimeError):
        JinjaFormatter('dummy')


def test_colorizing_support(logger):
    from logbook.more import ColorizedStderrHandler

    class TestColorizingHandler(ColorizedStderrHandler):

        def should_colorize(self, record):
            return True
        stream = StringIO()
    with TestColorizingHandler(format_string='{record.message}') as handler:
        logger.error('An error')
        logger.warn('A warning')
        logger.debug('A debug message')
        lines = handler.stream.getvalue().rstrip('\n').splitlines()
        assert lines == [
            '\x1b[31;01mAn error\x1b[39;49;00m',
            '\x1b[33;01mA warning\x1b[39;49;00m',
            '\x1b[37mA debug message\x1b[39;49;00m']


def test_tagged(default_handler):
    from logbook.more import TaggingLogger, TaggingHandler
    stream = StringIO()
    second_handler = logbook.StreamHandler(stream)

    logger = TaggingLogger('name', ['cmd'])
    handler = TaggingHandler(dict(
        info=default_handler,
        cmd=second_handler,
        both=[default_handler, second_handler],
    ))
    handler.bubble = False

    with handler:
        with capturing_stderr_context() as captured:
            logger.log('info', 'info message')
            logger.log('both', 'all message')
            logger.cmd('cmd message')

    stderr = captured.getvalue()

    assert 'info message' in stderr
    assert 'all message' in stderr
    assert 'cmd message' not in stderr

    stringio = stream.getvalue()

    assert 'info message' not in stringio
    assert 'all message' in stringio
    assert 'cmd message' in stringio


def test_tagging_logger(default_handler):
    from logbook import StderrHandler
    from logbook.more import TaggingLogger
    stream = StringIO()

    logger = TaggingLogger('tagged', ['a', 'b'])
    handler = StderrHandler(format_string="{record.msg}|{record.extra[tags]}")

    with handler:
        with capturing_stderr_context() as captured:
            logger.a("a")
            logger.b("b")

    stderr = captured.getvalue()

    assert "a|['a']" in stderr
    assert "a|['b']" not in stderr
    assert "b|['b']" in stderr
    assert "b|['a']" not in stderr


def test_external_application_handler(tmpdir, logger):
    from logbook.more import ExternalApplicationHandler as Handler
    fn = tmpdir.join('tempfile')
    handler = Handler([sys.executable, '-c', r'''if 1:
    f = open(%(tempfile)s, 'w')
    try:
        f.write('{record.message}\n')
    finally:
        f.close()
    ''' % {'tempfile': repr(str(fn))}])
    with handler:
        logger.error('this is a really bad idea')
    with fn.open() as rf:
        contents = rf.read().strip()
    assert contents == 'this is a really bad idea'


def test_exception_handler(logger):
    from logbook.more import ExceptionHandler

    with ExceptionHandler(ValueError):
        with pytest.raises(ValueError) as caught:
            logger.info('here i am')
    assert 'INFO: testlogger: here i am' in caught.value.args[0]


def test_exception_handler_specific_level(logger):
    from logbook.more import ExceptionHandler
    with logbook.TestHandler() as test_handler:
        with pytest.raises(ValueError) as caught:
            with ExceptionHandler(ValueError, level='WARNING'):
                logger.info('this is irrelevant')
                logger.warn('here i am')
        assert 'WARNING: testlogger: here i am' in caught.value.args[0]
    assert 'this is irrelevant' in test_handler.records[0].message


def test_dedup_handler(logger):
    from logbook.more import DedupHandler
    with logbook.TestHandler() as test_handler:
        with DedupHandler():
            logger.info('foo')
            logger.info('bar')
            logger.info('foo')
    assert 2 == len(test_handler.records)
    assert 'message repeated 2 times: foo' in test_handler.records[0].message
    assert 'message repeated 1 times: bar' in test_handler.records[1].message
