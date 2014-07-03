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
