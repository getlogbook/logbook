import base64
import re
import ssl
from unittest.mock import ANY, call, patch

import logbook

from .utils import capturing_stderr_context, make_fake_mail_handler

__file_without_pyc__ = __file__
if __file_without_pyc__.endswith(".pyc"):
    __file_without_pyc__ = __file_without_pyc__[:-1]


def test_mail_handler(activation_strategy, logger):
    subject = "\xf8nicode"
    handler = make_fake_mail_handler(subject=subject)
    with capturing_stderr_context() as fallback:
        with activation_strategy(handler):
            logger.warn("This is not mailed")
            try:
                1 / 0
            except Exception:
                logger.exception("Viva la Espa\xf1a")

        if not handler.mails:
            # if sending the mail failed, the reason should be on stderr
            assert False, fallback.getvalue()

        assert len(handler.mails) == 1
        sender, receivers, mail = handler.mails[0]
        mail = mail.replace("\r", "")
        assert sender == handler.from_addr
        assert "=?utf-8?q?=C3=B8nicode?=" in mail
        header, data = mail.split("\n\n", 1)
        if "Content-Transfer-Encoding: base64" in header:
            data = base64.b64decode(data).decode("utf-8")
        assert re.search(r"Message type:\s+ERROR", data)
        assert re.search(r"Location:.*%s" % re.escape(__file_without_pyc__), data)
        assert re.search(r"Module:\s+%s" % __name__, data)
        assert re.search(r"Function:\s+test_mail_handler", data)
        body = "Viva la Espa\xf1a"
        assert body in data
        assert "\nTraceback (most" in data
        assert "1 / 0" in data
        assert "This is not mailed" in fallback.getvalue()


def test_mail_handler_batching(activation_strategy, logger):
    mail_handler = make_fake_mail_handler()
    handler = logbook.FingersCrossedHandler(mail_handler, reset=True)
    with activation_strategy(handler):
        logger.warn("Testing")
        logger.debug("Even more")
        logger.error("And this triggers it")
        logger.info("Aha")
        logger.error("And this triggers it again!")

    assert len(mail_handler.mails) == 2
    mail = mail_handler.mails[0][2]

    pieces = mail.split("Log records that led up to this one:")
    assert len(pieces) == 2
    body, rest = pieces
    rest = rest.replace("\r", "")

    assert re.search(r"Message type:\s+ERROR", body)
    assert re.search(r"Module:\s+%s" % __name__, body)
    assert re.search(r"Function:\s+test_mail_handler_batching", body)

    related = rest.strip().split("\n\n")
    assert len(related) == 2
    assert re.search(r"Message type:\s+WARNING", related[0])
    assert re.search(r"Message type:\s+DEBUG", related[1])

    assert "And this triggers it again" in mail_handler.mails[1][2]


def test_group_handler_mail_combo(activation_strategy, logger):
    mail_handler = make_fake_mail_handler(level=logbook.DEBUG)
    handler = logbook.GroupHandler(mail_handler)
    with activation_strategy(handler):
        logger.error("The other way round")
        logger.warn("Testing")
        logger.debug("Even more")
        assert mail_handler.mails == []

    assert len(mail_handler.mails) == 1
    mail = mail_handler.mails[0][2]

    pieces = mail.split("Other log records in the same group:")
    assert len(pieces) == 2
    body, rest = pieces
    rest = rest.replace("\r", "")

    assert re.search(r"Message type:\s+ERROR", body)
    assert re.search(r"Module:\s+" + __name__, body)
    assert re.search(r"Function:\s+test_group_handler_mail_combo", body)

    related = rest.strip().split("\n\n")
    assert len(related) == 2
    assert re.search(r"Message type:\s+WARNING", related[0])
    assert re.search(r"Message type:\s+DEBUG", related[1])


def test_mail_handler_arguments():
    patch_smtp = patch("smtplib.SMTP", autospec=True)
    patch_load_cert_chain = patch("ssl.SSLContext.load_cert_chain", autospec=True)

    with patch_load_cert_chain as mock_load_cert_chain:
        with patch_smtp as mock_smtp:
            # Test the mail handler with supported arguments before changes to
            # secure, credentials, and starttls
            mail_handler = logbook.MailHandler(
                from_addr="from@example.com",
                recipients="to@example.com",
                server_addr=("server.example.com", 465),
                credentials=("username", "password"),
                secure=("keyfile", "certfile"),
            )

            mail_handler.get_connection()

            mock_smtp.assert_called_once_with("server.example.com", 465)
            mock_smtp().starttls.assert_called_once_with(context=ANY)
            assert isinstance(
                mock_smtp().starttls.call_args.kwargs["context"], ssl.SSLContext
            )
            mock_smtp().login.assert_called_once_with("username", "password")
            mock_load_cert_chain.assert_called_once_with("certfile", "keyfile")
            mock_smtp.reset_mock()
            mock_load_cert_chain.reset_mock()

            # Test secure=()
            mail_handler = logbook.MailHandler(
                from_addr="from@example.com",
                recipients="to@example.com",
                server_addr=("server.example.com", 465),
                credentials=("username", "password"),
                secure=(),
            )

            mail_handler.get_connection()

            mock_smtp.assert_called_once_with("server.example.com", 465)
            mock_smtp().starttls.assert_called_once_with(context=None)
            mock_smtp().login.assert_called_once_with("username", "password")
            mock_load_cert_chain.assert_not_called()
            mock_smtp.reset_mock()
            mock_load_cert_chain.reset_mock()

            # Test implicit port with string server_addr, dictionary credentials,
            # dictionary secure.
            mail_handler = logbook.MailHandler(
                from_addr="from@example.com",
                recipients="to@example.com",
                server_addr="server.example.com",
                credentials={"user": "username", "password": "password"},
                secure={"certfile": "certfile2", "keyfile": "keyfile2"},
            )

            mail_handler.get_connection()

            mock_smtp.assert_called_once_with("server.example.com", 587)
            mock_smtp().starttls.assert_called_once_with(context=ANY)
            assert isinstance(
                mock_smtp().starttls.call_args.kwargs["context"], ssl.SSLContext
            )
            mock_smtp().login.assert_called_once_with("username", "password")
            mock_load_cert_chain.assert_called_once_with("certfile2", "keyfile2")
            mock_smtp.reset_mock()
            mock_load_cert_chain.reset_mock()

            # Test default port for non-secure connection
            mail_handler = logbook.MailHandler(
                from_addr="from@example.com",
                recipients="to@example.com",
                server_addr="server.example.com",
            )

            mail_handler.get_connection()

            mock_smtp.assert_called_once_with("server.example.com", 25)
            mock_smtp().starttls.assert_not_called()
            mock_load_cert_chain.assert_not_called()
            mock_smtp.reset_mock()
            mock_load_cert_chain.reset_mock()

            # Test default host and port for non-secure connection
            mail_handler = logbook.MailHandler(
                from_addr="from@example.com",
                recipients="to@example.com",
            )

            mail_handler.get_connection()

            mock_smtp.assert_called_once_with("127.0.0.1", 25)
            mock_smtp().starttls.assert_not_called()
            mock_load_cert_chain.assert_not_called()
            mock_smtp.reset_mock()
            mock_load_cert_chain.reset_mock()

            # Test default host and port for starttls connection
            mail_handler = logbook.MailHandler(
                from_addr="from@example.com",
                recipients="to@example.com",
                secure=True,
            )

            mail_handler.get_connection()

            mock_smtp.assert_called_once_with("127.0.0.1", 587)
            mock_smtp().starttls.assert_called_once_with(context=None)
            mock_load_cert_chain.assert_not_called()
            mock_smtp.reset_mock()
            mock_load_cert_chain.reset_mock()

            # Test secure=True
            mail_handler = logbook.MailHandler(
                from_addr="from@example.com",
                recipients="to@example.com",
                server_addr=("server.example.com", 465),
                credentials=("username", "password"),
                secure=True,
            )

            mail_handler.get_connection()

            mock_smtp.assert_called_once_with("server.example.com", 465)
            mock_smtp().starttls.assert_called_once_with(context=None)
            mock_smtp().login.assert_called_once_with("username", "password")
            mock_load_cert_chain.assert_not_called()
            mock_smtp.reset_mock()
            mock_load_cert_chain.reset_mock()

            # Test secure=False
            mail_handler = logbook.MailHandler(
                from_addr="from@example.com",
                recipients="to@example.com",
                server_addr=("server.example.com", 465),
                credentials=("username", "password"),
                secure=False,
            )

            mail_handler.get_connection()

            mock_smtp.assert_called_once_with("server.example.com", 465)
            mock_smtp().starttls.assert_not_called()
            mock_smtp().login.assert_called_once_with("username", "password")
            mock_load_cert_chain.assert_not_called()
            mock_smtp.reset_mock()
            mock_load_cert_chain.reset_mock()

            # Test SSLContext
            context = ssl.create_default_context()
            mail_handler = logbook.MailHandler(
                from_addr="from@example.com",
                recipients="to@example.com",
                server_addr=("server.example.com", 465),
                credentials=("username", "password"),
                secure=context,
            )

            mail_handler.get_connection()

            mock_smtp.assert_called_once_with("server.example.com", 465)
            mock_smtp().starttls.assert_called_once_with(context=context)
            mock_smtp().login.assert_called_once_with("username", "password")
            mock_load_cert_chain.assert_not_called()

        with patch("smtplib.SMTP_SSL", autospec=True) as mock_smtp_ssl:
            # Test starttls=False
            mail_handler = logbook.MailHandler(
                from_addr="from@example.com",
                recipients="to@example.com",
                server_addr="server.example.com",
                credentials={"user": "username", "password": "password"},
                secure={"certfile": "certfile", "keyfile": "keyfile"},
                starttls=False,
            )

            mail_handler.get_connection()

            mock_smtp_ssl.assert_called_once_with(
                "server.example.com", 465, context=ANY
            )
            assert isinstance(mock_smtp_ssl.call_args.kwargs["context"], ssl.SSLContext)
            mock_load_cert_chain.assert_called_once_with("certfile", "keyfile")
            mock_smtp().login.assert_called_once_with("username", "password")
            mock_smtp_ssl.reset_mock()
            mock_load_cert_chain.reset_mock()

            # Test starttls=False with secure=True
            mail_handler = logbook.MailHandler(
                from_addr="from@example.com",
                recipients="to@example.com",
                server_addr="server.example.com",
                credentials={"user": "username", "password": "password"},
                secure=True,
                starttls=False,
            )

            mail_handler.get_connection()

            mock_smtp_ssl.assert_called_once_with(
                "server.example.com", 465, context=None
            )
            mock_smtp_ssl().starttls.assert_not_called()
            mock_smtp().login.assert_called_once_with("username", "password")
            mock_load_cert_chain.assert_not_called()
            mock_smtp_ssl.reset_mock()
            mock_load_cert_chain.reset_mock()

            # Test default host and port for starttls connection
            mail_handler = logbook.MailHandler(
                from_addr="from@example.com",
                recipients="to@example.com",
                secure=True,
                starttls=False,
            )

            mail_handler.get_connection()

            mock_smtp_ssl.assert_called_once_with("127.0.0.1", 465, context=None)
            mock_smtp_ssl().starttls.assert_not_called()
            mock_load_cert_chain.assert_not_called()
            mock_smtp_ssl.reset_mock()
            mock_load_cert_chain.reset_mock()

            # Test SSLContext
            context = ssl.create_default_context()
            mail_handler = logbook.MailHandler(
                from_addr="from@example.com",
                recipients="to@example.com",
                server_addr="server.example.com",
                credentials={"user": "username", "password": "password"},
                secure=context,
                starttls=False,
            )

            mail_handler.get_connection()

            mock_smtp_ssl.assert_called_once_with(
                "server.example.com", 465, context=context
            )
            mock_smtp_ssl().starttls.assert_not_called()
            mock_smtp().login.assert_called_once_with("username", "password")
            mock_load_cert_chain.assert_not_called()
