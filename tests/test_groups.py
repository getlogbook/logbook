import logbook


def test_groups(logger):
    def inject_extra(record):
        record.extra['foo'] = 'bar'
    group = logbook.LoggerGroup(processor=inject_extra)
    group.level = logbook.ERROR
    group.add_logger(logger)
    with logbook.TestHandler() as handler:
        logger.warn('A warning')
        logger.error('An error')
    assert (not handler.has_warning('A warning'))
    assert handler.has_error('An error')
    assert handler.records[0].extra['foo'] == 'bar'


def test_group_disabled():
    group = logbook.LoggerGroup()
    logger1 = logbook.Logger('testlogger1')
    logger2 = logbook.Logger('testlogger2')

    group.add_logger(logger1)
    group.add_logger(logger2)

    # Test group disable

    group.disable()

    with logbook.TestHandler() as handler:
        logger1.warn('Warning 1')
        logger2.warn('Warning 2')

    assert not handler.has_warnings

    # Test group enable

    group.enable()

    with logbook.TestHandler() as handler:
        logger1.warn('Warning 1')
        logger2.warn('Warning 2')

    assert handler.has_warning('Warning 1')
    assert handler.has_warning('Warning 2')

    # Test group disabled, but logger explicitly enabled

    group.disable()

    logger1.enable()

    with logbook.TestHandler() as handler:
        logger1.warn('Warning 1')
        logger2.warn('Warning 2')

    assert handler.has_warning('Warning 1')
    assert not handler.has_warning('Warning 2')

    # Logger 1 will be enabled by using force=True

    group.disable(force=True)

    with logbook.TestHandler() as handler:
        logger1.warn('Warning 1')
        logger2.warn('Warning 2')

    assert not handler.has_warning('Warning 1')
    assert not handler.has_warning('Warning 2')

    # Enabling without force means logger 1 will still be disabled.

    group.enable()

    with logbook.TestHandler() as handler:
        logger1.warn('Warning 1')
        logger2.warn('Warning 2')

    assert not handler.has_warning('Warning 1')
    assert handler.has_warning('Warning 2')

    # Force logger 1 enabled.

    group.enable(force=True)

    with logbook.TestHandler() as handler:
        logger1.warn('Warning 1')
        logger2.warn('Warning 2')

    assert handler.has_warning('Warning 1')
    assert handler.has_warning('Warning 2')
