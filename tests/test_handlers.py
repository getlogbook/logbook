import logbook

from .utils import capturing_stderr_context, make_fake_mail_handler


def test_custom_logger(activation_strategy, logger):
    client_ip = '127.0.0.1'

    class CustomLogger(logbook.Logger):

        def process_record(self, record):
            record.extra['ip'] = client_ip

    custom_log = CustomLogger('awesome logger')
    fmt = ('[{record.level_name}] {record.channel}: '
           '{record.message} [{record.extra[ip]}]')
    handler = logbook.TestHandler(format_string=fmt)
    assert handler.format_string == fmt

    with activation_strategy(handler):
        custom_log.warn('Too many sounds')
        logger.warn('"Music" playing')

    assert handler.formatted_records == [
        '[WARNING] awesome logger: Too many sounds [127.0.0.1]',
        '[WARNING] testlogger: "Music" playing []']


def test_custom_handling(activation_strategy, logger):
    class MyTestHandler(logbook.TestHandler):
        def handle(self, record):
            if record.extra.get('flag') != 'testing':
                return False
            return logbook.TestHandler.handle(self, record)

    # Check metaclass (== cls.__class__)
    assert logbook.Handler.__class__ == logbook.handlers._HandlerType

    class MyLogger(logbook.Logger):
        def process_record(self, record):
            logbook.Logger.process_record(self, record)
            record.extra['flag'] = 'testing'

    log = MyLogger()
    handler = MyTestHandler()
    with capturing_stderr_context() as captured:
        with activation_strategy(handler):
            log.warn('From my logger')
            logger.warn('From another logger')
        assert handler.has_warning('From my logger')
        assert 'From another logger' in captured.getvalue()


def test_nested_setups(activation_strategy):
    with capturing_stderr_context() as captured:
        logger = logbook.Logger('App')
        test_handler = logbook.TestHandler(level='WARNING')
        mail_handler = make_fake_mail_handler(bubble=True)

        handlers = logbook.NestedSetup([
            logbook.NullHandler(),
            test_handler,
            mail_handler
        ])

        with activation_strategy(handlers):
            logger.warn('This is a warning')
            logger.error('This is also a mail')
            try:
                1 / 0
            except Exception:
                logger.exception()
        logger.warn('And here we go straight back to stderr')

        assert test_handler.has_warning('This is a warning')
        assert test_handler.has_error('This is also a mail')
        assert len(mail_handler.mails) == 2
        assert 'This is also a mail' in mail_handler.mails[0][2]
        assert '1 / 0' in mail_handler.mails[1][2]
        assert 'And here we go straight back to stderr' in captured.getvalue()

        with activation_strategy(handlers):
            logger.warn('threadbound warning')

        handlers.push_application()
        try:
            logger.warn('applicationbound warning')
        finally:
            handlers.pop_application()


def test_filtering(activation_strategy):
    logger1 = logbook.Logger('Logger1')
    logger2 = logbook.Logger('Logger2')
    handler = logbook.TestHandler()
    outer_handler = logbook.TestHandler()

    def only_1(record, handler):
        return record.dispatcher is logger1
    handler.filter = only_1

    with activation_strategy(outer_handler):
        with activation_strategy(handler):
            logger1.warn('foo')
            logger2.warn('bar')

    assert handler.has_warning('foo', channel='Logger1')
    assert (not handler.has_warning('bar', channel='Logger2'))
    assert (not outer_handler.has_warning('foo', channel='Logger1'))
    assert outer_handler.has_warning('bar', channel='Logger2')


def test_different_context_pushing(activation_strategy):
    h1 = logbook.TestHandler(level=logbook.DEBUG)
    h2 = logbook.TestHandler(level=logbook.INFO)
    h3 = logbook.TestHandler(level=logbook.WARNING)
    logger = logbook.Logger('Testing')

    with activation_strategy(h1):
        with activation_strategy(h2):
            with activation_strategy(h3):
                logger.warn('Wuuu')
                logger.info('still awesome')
                logger.debug('puzzled')

    assert h1.has_debug('puzzled')
    assert h2.has_info('still awesome')
    assert h3.has_warning('Wuuu')
    for handler in h1, h2, h3:
        assert len(handler.records) == 1


def test_default_handlers(logger):
    with capturing_stderr_context() as stream:
        logger.warn('Aha!')
        captured = stream.getvalue()
    assert 'WARNING: testlogger: Aha!' in captured
