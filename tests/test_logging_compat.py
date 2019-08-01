import functools
from random import randrange

import logbook
import logbook.compat
from logbook.helpers import StringIO

import pytest

from .utils import capturing_stderr_context


__file_without_pyc__ = __file__
if __file_without_pyc__.endswith(".pyc"):
    __file_without_pyc__ = __file_without_pyc__[:-1]


@pytest.mark.parametrize('set_root_logger_level', [True, False])
def test_basic_compat(request, set_root_logger_level):
    import logging
    from logbook.compat import redirected_logging

    # mimic the default logging setting
    request.addfinalizer(functools.partial(
        logging.root.setLevel, logging.root.level))
    logging.root.setLevel(logging.WARNING)

    name = 'test_logbook-%d' % randrange(1 << 32)
    logger = logging.getLogger(name)

    with logbook.TestHandler(bubble=True) as handler:
        with capturing_stderr_context() as captured:
            with redirected_logging(set_root_logger_level):
                logger.debug('This is from the old system')
                logger.info('This is from the old system')
                logger.warning('This is from the old %s', 'system')
                logger.error('This is from the old system')
                logger.critical('This is from the old system')
                logger.error('This is a %(what)s %(where)s', {'what': 'mapping', 'where': 'test'})
        assert ('WARNING: %s: This is from the old system' %
                name) in captured.getvalue()
        assert ('ERROR: %s: This is a mapping test' %
                name) in captured.getvalue()
    if set_root_logger_level:
        assert handler.records[0].level == logbook.DEBUG
    else:
        assert handler.records[0].level == logbook.WARNING
        assert handler.records[0].msg == 'This is from the old %s'


def test_redirect_logbook():
    import logging
    out = StringIO()
    logger = logging.getLogger()
    logbook_logger = logbook.Logger('testlogger')
    old_handlers = logger.handlers[:]
    handler = logging.StreamHandler(out)
    handler.setFormatter(logging.Formatter(
        '%(name)s:%(levelname)s:%(message)s'))
    logger.handlers[:] = [handler]
    try:
        with logbook.compat.LoggingHandler():
            logbook_logger.warn("This goes to logging")
            pieces = out.getvalue().strip().split(':')
            assert pieces == ['testlogger', 'WARNING', 'This goes to logging']
    finally:
        logger.handlers[:] = old_handlers


def test_redirect_logbook_respect_specific_configuration():
    import logging
    import logging.config
    out1 = StringIO()
    out2 = StringIO()
    config = {
        'version': 1,
        'formatters': {
            'brief': {
                'format': '%(name)s:%(levelname)s:%(message)s'
            }
        },
        'handlers': {
            'console_1': {
                'class': 'logging.StreamHandler',
                'stream': out1,
                'level': 'INFO',
            },
            'console_2': {
                'class': 'logging.StreamHandler',
                'stream': out2,
                'level': 'INFO',
                'formatter': 'brief'
            },
        },
        'root': {
            'level': 'INFO',
            'handlers': ['console_1'],
        },
        'loggers': {
            'module_2': {
                'handlers': ['console_2'],
                'propagate': False
            }
        },
    }
    logger = logging.getLogger()
    logbook_logger = logbook.Logger('module_2')
    old_handlers = logger.handlers[:]
    logging.config.dictConfig(config)
    try:
        with logbook.compat.LoggingHandler():
            logbook_logger.warn("This goes to logging")
            pieces = out2.getvalue().strip().split(':')
            # Check if our message goes to console_2
            assert pieces == ['module_2', 'WARNING', 'This goes to logging']
            # Check that our message doesn't go to console_1
            assert out1.getvalue() == ''
    finally:
        logger.handlers[:] = old_handlers


from itertools import count
test_warning_redirections_i = count()


def test_warning_redirections():
    from logbook.compat import redirected_warnings
    with logbook.TestHandler() as handler:
        redirector = redirected_warnings()
        redirector.start()
        try:
            from warnings import warn, resetwarnings
            resetwarnings()
            warn(RuntimeWarning('Testing' + str(next(test_warning_redirections_i))))
        finally:
            redirector.end()

    assert len(handler.records) == 1
    assert handler.formatted_records[0].startswith(
        '[WARNING] RuntimeWarning: Testing')
    assert __file_without_pyc__ in handler.records[0].filename
