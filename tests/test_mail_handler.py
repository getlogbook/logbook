import base64
import re
import sys

import logbook
from logbook.helpers import u

from .utils import capturing_stderr_context, make_fake_mail_handler

try:
    from unittest.mock import Mock, call, patch
except ImportError:
    from mock import Mock, call, patch

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
        assert re.search('Location:.*%s' %
                         re.escape(__file_without_pyc__), data)
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


def test_mail_handler_arguments():
    with patch('smtplib.SMTP', autospec=True) as mock_smtp:

        # Test the mail handler with supported arguments before changes to
        # secure, credentials, and starttls
        mail_handler = logbook.MailHandler(
            from_addr='from@example.com',
            recipients='to@example.com',
            server_addr=('server.example.com', 465),
            credentials=('username', 'password'),
            secure=('keyfile', 'certfile'))

        mail_handler.get_connection()

        assert mock_smtp.call_args == call('server.example.com', 465)
        assert mock_smtp.method_calls[1] == call().starttls(
            keyfile='keyfile', certfile='certfile')
        assert mock_smtp.method_calls[3] == call().login('username', 'password')

        # Test secure=()
        mail_handler = logbook.MailHandler(
            from_addr='from@example.com',
            recipients='to@example.com',
            server_addr=('server.example.com', 465),
            credentials=('username', 'password'),
            secure=())

        mail_handler.get_connection()

        assert mock_smtp.call_args == call('server.example.com', 465)
        assert mock_smtp.method_calls[5] == call().starttls(
            certfile=None, keyfile=None)
        assert mock_smtp.method_calls[7] == call().login('username', 'password')

        # Test implicit port with string server_addr, dictionary credentials,
        # dictionary secure.
        mail_handler = logbook.MailHandler(
            from_addr='from@example.com',
            recipients='to@example.com',
            server_addr='server.example.com',
            credentials={'user': 'username', 'password': 'password'},
            secure={'certfile': 'certfile2', 'keyfile': 'keyfile2'})

        mail_handler.get_connection()

        assert mock_smtp.call_args == call('server.example.com', 465)
        assert mock_smtp.method_calls[9] == call().starttls(
            certfile='certfile2', keyfile='keyfile2')
        assert mock_smtp.method_calls[11] == call().login(
            user='username', password='password')

        # Test secure=True
        mail_handler = logbook.MailHandler(
            from_addr='from@example.com',
            recipients='to@example.com',
            server_addr=('server.example.com', 465),
            credentials=('username', 'password'),
            secure=True)

        mail_handler.get_connection()

        assert mock_smtp.call_args == call('server.example.com', 465)
        assert mock_smtp.method_calls[13] == call().starttls(
            certfile=None, keyfile=None)
        assert mock_smtp.method_calls[15] == call().login('username', 'password')
        assert len(mock_smtp.method_calls) == 16

        # Test secure=False
        mail_handler = logbook.MailHandler(
            from_addr='from@example.com',
            recipients='to@example.com',
            server_addr=('server.example.com', 465),
            credentials=('username', 'password'),
            secure=False)

        mail_handler.get_connection()

        # starttls not called because we check len of method_calls before and
        # after this test.
        assert mock_smtp.call_args == call('server.example.com', 465)
        assert mock_smtp.method_calls[16] == call().login('username', 'password')
        assert len(mock_smtp.method_calls) == 17

    with patch('smtplib.SMTP_SSL', autospec=True) as mock_smtp_ssl:
        # Test starttls=False
        mail_handler = logbook.MailHandler(
            from_addr='from@example.com',
            recipients='to@example.com',
            server_addr='server.example.com',
            credentials={'user': 'username', 'password': 'password'},
            secure={'certfile': 'certfile', 'keyfile': 'keyfile'},
            starttls=False)

        mail_handler.get_connection()

        assert mock_smtp_ssl.call_args == call(
            'server.example.com', 465, keyfile='keyfile', certfile='certfile')
        assert mock_smtp_ssl.method_calls[0] == call().login(
            user='username', password='password')

        # Test starttls=False with secure=True
        mail_handler = logbook.MailHandler(
            from_addr='from@example.com',
            recipients='to@example.com',
            server_addr='server.example.com',
            credentials={'user': 'username', 'password': 'password'},
            secure=True,
            starttls=False)

        mail_handler.get_connection()

        assert mock_smtp_ssl.call_args == call(
            'server.example.com', 465, keyfile=None, certfile=None)
        assert mock_smtp_ssl.method_calls[1] == call().login(
            user='username', password='password')






