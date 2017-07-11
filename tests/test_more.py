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
        def __init__(self, *args, **kwargs):
            super(TestColorizingHandler, self).__init__(*args, **kwargs)
            self._obj_stream = StringIO()

        @property
        def stream(self):
            return self._obj_stream

    with TestColorizingHandler(format_string='{record.message}') as handler:
        handler.force_color()
        logger.error('An error')
        logger.warn('A warning')
        logger.debug('A debug message')
        lines = handler.stream.getvalue().rstrip('\n').splitlines()
        assert lines == [
            '\x1b[31;01mAn error\x1b[39;49;00m',
            '\x1b[33;01mA warning\x1b[39;49;00m',
            '\x1b[37mA debug message\x1b[39;49;00m']

    with TestColorizingHandler(format_string='{record.message}') as handler:
        handler.forbid_color()
        logger.error('An error')
        logger.warn('A warning')
        logger.debug('A debug message')
        lines = handler.stream.getvalue().rstrip('\n').splitlines()
        assert lines == ['An error', 'A warning', 'A debug message']



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


class TestRiemannHandler(object):

    @require_module("riemann_client")
    def test_happy_path(self, logger):
        from logbook.more import RiemannHandler
        riemann_handler = RiemannHandler("127.0.0.1", 5555, message_type="test", level=logbook.INFO)
        null_handler = logbook.NullHandler()
        with null_handler.applicationbound():
            with riemann_handler:
                logger.error("Something bad has happened")
                try:
                    raise RuntimeError("For example, a RuntimeError")
                except Exception as ex:
                    logger.exception(ex)
                logger.info("But now it is ok")

        q = riemann_handler.queue
        assert len(q) == 3
        error_event = q[0]
        assert error_event["state"] == "error"
        exc_event = q[1]
        assert exc_event["description"] == "For example, a RuntimeError"
        info_event = q[2]
        assert info_event["state"] == "ok"

    @require_module("riemann_client")
    def test_incorrect_type(self):
        from logbook.more import RiemannHandler
        with pytest.raises(RuntimeError):
            RiemannHandler("127.0.0.1", 5555, message_type="fancy_type")

    @require_module("riemann_client")
    def test_flush(self, logger):
        from logbook.more import RiemannHandler
        riemann_handler = RiemannHandler("127.0.0.1",
                                         5555,
                                         message_type="test",
                                         flush_threshold=2,
                                         level=logbook.INFO)
        null_handler = logbook.NullHandler()
        with null_handler.applicationbound():
            with riemann_handler:
                logger.info("Msg #1")
                logger.info("Msg #2")
                logger.info("Msg #3")

        q = riemann_handler.queue
        assert len(q) == 1
        assert q[0]["description"] == "Msg #3"
