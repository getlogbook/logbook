import logbook
import pytest

from .utils import capturing_stderr_context


def test_fingerscrossed(activation_strategy, logger, default_handler):
    handler = logbook.FingersCrossedHandler(default_handler,
                                            logbook.WARNING)

    # if no warning occurs, the infos are not logged
    with activation_strategy(handler):
        with capturing_stderr_context() as captured:
            logger.info('some info')
        assert captured.getvalue() == ''
        assert (not handler.triggered)

    # but if it does, all log messages are output
    with activation_strategy(handler):
        with capturing_stderr_context() as captured:
            logger.info('some info')
            logger.warning('something happened')
            logger.info('something else happened')
        logs = captured.getvalue()
        assert 'some info' in logs
        assert 'something happened' in logs
        assert 'something else happened' in logs
        assert handler.triggered


def test_fingerscrossed_factory(activation_strategy, logger):
    handlers = []

    def handler_factory(record, fch):
        handler = logbook.TestHandler()
        handlers.append(handler)
        return handler

    def make_fch():
        return logbook.FingersCrossedHandler(handler_factory,
                                             logbook.WARNING)

    fch = make_fch()
    with activation_strategy(fch):
        logger.info('some info')
        assert len(handlers) == 0
        logger.warning('a warning')
        assert len(handlers) == 1
        logger.error('an error')
        assert len(handlers) == 1
        assert handlers[0].has_infos
        assert handlers[0].has_warnings
        assert handlers[0].has_errors
        assert (not handlers[0].has_notices)
        assert (not handlers[0].has_criticals)
        assert (not handlers[0].has_debugs)

    fch = make_fch()
    with activation_strategy(fch):
        logger.info('some info')
        logger.warning('a warning')
        assert len(handlers) == 2


def test_fingerscrossed_buffer_size(activation_strategy):
    logger = logbook.Logger('Test')
    test_handler = logbook.TestHandler()
    handler = logbook.FingersCrossedHandler(test_handler, buffer_size=3)

    with activation_strategy(handler):
        logger.info('Never gonna give you up')
        logger.warn('Aha!')
        logger.warn('Moar!')
        logger.error('Pure hate!')

    assert test_handler.formatted_records == ['[WARNING] Test: Aha!', '[WARNING] Test: Moar!', '[ERROR] Test: Pure hate!']

