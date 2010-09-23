from logbook import Logger


log = Logger('Test logger')
log.disabled = True


def run():
    for x in xrange(500):
        log.warning('this is not handled')
