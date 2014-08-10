import base64
import re
import sys

import logbook
from logbook.helpers import u

from .utils import capturing_stderr_context, make_fake_mail_handler

__file_without_pyc__ = __file__
if __file_without_pyc__.endswith('.pyc'):
    __file_without_pyc__ = __file_without_pyc__[:-1]


def test_mail_handler(activation_strategy, logger):
    subject = u('\xf8nicode')
    handler = make_fake_mail_handler(subject=subject)
    with capturing_stderr_context() as fallback:
        with activation_strategy(handler):
            logger.warn('This is not mailed')
            try:
                1 / 0
            except Exception:
                logger.exception(u('Viva la Espa\xf1a'))

        if not handler.mails:
            # if sending the mail failed, the reason should be on stderr
            assert False, fallback.getvalue()

        assert len(handler.mails) == 1
        sender, receivers, mail = handler.mails[0]
        mail = mail.replace('\r', '')
        assert sender == handler.from_addr
        assert '=?utf-8?q?=C3=B8nicode?=' in mail
        header, data = mail.split('\n\n', 1)
        if 'Content-Transfer-Encoding: base64' in header:
            data = base64.b64decode(data).decode('utf-8')
        assert re.search('Message type:\s+ERROR', data)
        assert re.search('Location:.*%s' % re.escape(__file_without_pyc__), data)
        assert re.search('Module:\s+%s' % __name__, data)
        assert re.search('Function:\s+test_mail_handler', data)
        body = u('Viva la Espa\xf1a')
        if sys.version_info < (3, 0):
            body = body.encode('utf-8')
        assert body in data
        assert '\nTraceback (most' in data
        assert '1 / 0' in data
        assert 'This is not mailed' in fallback.getvalue()


def test_mail_handler_batching(activation_strategy, logger):
    mail_handler = make_fake_mail_handler()
    handler = logbook.FingersCrossedHandler(mail_handler, reset=True)
    with activation_strategy(handler):
        logger.warn('Testing')
        logger.debug('Even more')
        logger.error('And this triggers it')
        logger.info('Aha')
        logger.error('And this triggers it again!')

    assert len(mail_handler.mails) == 2
    mail = mail_handler.mails[0][2]

    pieces = mail.split('Log records that led up to this one:')
    assert len(pieces) == 2
    body, rest = pieces
    rest = rest.replace('\r', '')

    assert re.search('Message type:\s+ERROR', body)
    assert re.search('Module:\s+%s' % __name__, body)
    assert re.search('Function:\s+test_mail_handler_batching', body)

    related = rest.strip().split('\n\n')
    assert len(related) == 2
    assert re.search('Message type:\s+WARNING', related[0])
    assert re.search('Message type:\s+DEBUG', related[1])

    assert 'And this triggers it again' in mail_handler.mails[1][2]


def test_group_handler_mail_combo(activation_strategy, logger):
    mail_handler = make_fake_mail_handler(level=logbook.DEBUG)
    handler = logbook.GroupHandler(mail_handler)
    with activation_strategy(handler):
        logger.error('The other way round')
        logger.warn('Testing')
        logger.debug('Even more')
        assert mail_handler.mails == []

    assert len(mail_handler.mails) == 1
    mail = mail_handler.mails[0][2]

    pieces = mail.split('Other log records in the same group:')
    assert len(pieces) == 2
    body, rest = pieces
    rest = rest.replace('\r', '')

    assert re.search('Message type:\\s+ERROR', body)
    assert re.search('Module:\s+' + __name__, body)
    assert re.search('Function:\s+test_group_handler_mail_combo', body)

    related = rest.strip().split('\n\n')
    assert len(related) == 2
    assert re.search('Message type:\s+WARNING', related[0])
    assert re.search('Message type:\s+DEBUG', related[1])
