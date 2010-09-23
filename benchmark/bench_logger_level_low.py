from logbook import Logger, ERROR


log = Logger('Test logger')
log.level = ERROR


def run():
    for x in xrange(500):
        log.warning('this is not handled')
