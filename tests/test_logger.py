import logbook


def test_level_properties(logger):
    assert logger.level == logbook.NOTSET
    assert logger.level_name == 'NOTSET'
    logger.level_name = 'WARNING'
    assert logger.level == logbook.WARNING
    logger.level = logbook.ERROR
    assert logger.level_name == 'ERROR'


def test_reflected_properties(logger):
    group = logbook.LoggerGroup()
    group.add_logger(logger)
    assert logger.group == group
    group.level = logbook.ERROR
    assert logger.level == logbook.ERROR
    assert logger.level_name == 'ERROR'
    group.level = logbook.WARNING
    assert logger.level == logbook.WARNING
    assert logger.level_name == 'WARNING'
    logger.level = logbook.CRITICAL
    group.level = logbook.DEBUG
    assert logger.level == logbook.CRITICAL
    assert logger.level_name == 'CRITICAL'
    group.remove_logger(logger)
    assert logger.group is None
