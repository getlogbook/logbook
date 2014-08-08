import logbook

from .utils import capturing_stderr_context


def test_null_handler(activation_strategy, logger):
    with capturing_stderr_context() as captured:
        with activation_strategy(logbook.NullHandler()):
            with activation_strategy(logbook.TestHandler(level='ERROR')) as handler:
                logger.error('An error')
                logger.warn('A warning')
        assert captured.getvalue() == ''
        assert (not handler.has_warning('A warning'))
        assert handler.has_error('An error')


def test_blackhole_setting(activation_strategy):
    null_handler = logbook.NullHandler()
    heavy_init = logbook.LogRecord.heavy_init
    with activation_strategy(null_handler):
        def new_heavy_init(self):
            raise RuntimeError('should not be triggered')
        logbook.LogRecord.heavy_init = new_heavy_init
        try:
            with activation_strategy(null_handler):
                logbook.warn('Awesome')
        finally:
            logbook.LogRecord.heavy_init = heavy_init

    null_handler.bubble = True
    with capturing_stderr_context() as captured:
        logbook.warning('Not a blockhole')
        assert captured.getvalue() != ''


def test_null_handler_filtering(activation_strategy):
    logger1 = logbook.Logger("1")
    logger2 = logbook.Logger("2")
    outer = logbook.TestHandler()
    inner = logbook.NullHandler()

    inner.filter = lambda record, handler: record.dispatcher is logger1

    with activation_strategy(outer):
        with activation_strategy(inner):
            logger1.warn("1")
            logger2.warn("2")

    assert outer.has_warning('2', channel='2')
    assert (not outer.has_warning('1', channel='1'))
