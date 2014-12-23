import sys


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
