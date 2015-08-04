import sys

import logbook

from .utils import capturing_stderr_context


def test_exc_info_when_no_exceptions_exist(logger):
    with capturing_stderr_context() as captured:
        with logbook.StreamHandler(sys.stderr):
            logger.debug('message', exc_info=True)
    assert 'Traceback' not in captured.getvalue()

def test_exc_info_false():
    with logbook.handlers.TestHandler() as handler:
        logbook.debug('message here', exc_info=False)
    [record] = handler.records
    assert not record.formatted_exception


def test_extradict(active_handler, logger):
    logger.warn('Test warning')
    record = active_handler.records[0]
    record.extra['existing'] = 'foo'
    assert record.extra['nonexisting'] == ''
    assert record.extra['existing'] == 'foo'
    assert repr(record.extra) == "ExtraDict({'existing': 'foo'})"


def test_calling_frame(active_handler, logger):
    logger.warn('test')
    assert active_handler.records[0].calling_frame == sys._getframe()

def test_frame_correction(active_handler, logger):
    def inner():
        logger.warn('test', frame_correction=+1)

    inner()
    assert active_handler.records[0].calling_frame == sys._getframe()

def test_dispatcher(active_handler, logger):
    logger.warn('Logbook is too awesome for stdlib')
    assert active_handler.records[0].dispatcher == logger
