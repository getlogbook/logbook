from logbook import NTEventLogHandler, Logger

logger = Logger('MyLogger')
handler = NTEventLogHandler('My Application')

with handler.applicationbound():
    logger.error('Testing')
