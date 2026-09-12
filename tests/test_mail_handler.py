import base64
import email
import email.policy
import re
import socket
import ssl
from concurrent.futures import ThreadPoolExecutor
from smtplib import SMTPResponseException, SMTPServerDisconnected
from unittest.mock import ANY, patch

import pytest
from aiosmtpd.controller import Controller

import logbook

from .utils import (
    capturing_stderr_context,
    make_fake_mail_handler,
    unused_tcp_address,
)

__file_without_pyc__ = __file__
if __file_without_pyc__.endswith(".pyc"):
    __file_without_pyc__ = __file_without_pyc__[:-1]


@pytest.fixture
def local_hostname(monkeypatch):
    # Both smtplib and aiosmtpd look up this machine's fully qualified name
    # before they say EHLO or send a banner. On some CI runners that reverse
    # lookup hangs until the resolver gives up, which is long enough for the
    # other end to stop waiting. The name needs a dot in it, or smtplib
    # falls back to resolving the hostname instead, which hangs the same way.
    monkeypatch.setattr(socket, "getfqdn", lambda name="": "localhost.localdomain")


@pytest.mark.parametrize(
    ("secure", "expected"),
    [(False, SMTPServerDisconnected), (True, socket.timeout)],
)
def test_mail_timeout_with_stalled_server(logger, local_hostname, secure, expected):
    # A listening socket that is never accepted completes the TCP handshake
    # in the kernel, so the client connects and then waits for a greeting
    # (or a TLS hello) that never comes.
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        handler = logbook.MailHandler(
            "from@example.test",
            ["to@example.test"],
            server_addr=server.getsockname(),
            secure=secure,
            starttls=False,
            timeout=0.05,
        )
        with (
            handler,
            logbook.Flags(errors="raise"),
            pytest.raises(expected, match="timed out"),
        ):
            logger.error("stalled mail server")


def test_mail_connection_closed_when_setup_fails(logger, local_hostname):
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        server.settimeout(3)
        handler = logbook.MailHandler(
            "from@example.test",
            ["to@example.test"],
            server_addr=server.getsockname(),
            secure=True,
        )

        def refuse_starttls():
            with server.accept()[0] as connection:
                connection.settimeout(3)
                with connection.makefile("rwb", buffering=0) as stream:
                    stream.write(b"220 localhost test server\r\n")
                    stream.readline()
                    stream.write(b"250-localhost\r\n250 STARTTLS\r\n")
                    stream.readline()
                    stream.write(b"454 TLS unavailable\r\n")
                    try:
                        return stream.readline() == b""
                    except socket.timeout:
                        return False

        with ThreadPoolExecutor(max_workers=1) as executor:
            receiver = executor.submit(refuse_starttls)
            with (
                handler,
                logbook.Flags(errors="raise"),
                pytest.raises(SMTPResponseException) as caught,
            ):
                logger.error("no TLS today")
            # The traceback holds on to the connection object, so the socket
            # outlives the failure unless the handler closes it.
            assert receiver.result(timeout=5), "connection left open after failure"
            assert caught.value.smtp_code == 454


@pytest.mark.parametrize(
    "failure", [SMTPResponseException(535, b"no"), KeyboardInterrupt()]
)
def test_mail_connection_closed_when_login_fails(failure):
    with patch("smtplib.SMTP", autospec=True) as mock_smtp:
        mock_smtp().login.side_effect = failure
        handler = logbook.MailHandler(
            "from@example.test",
            ["to@example.test"],
            server_addr=("server.example.test", 25),
            credentials=("username", "password"),
        )
        with pytest.raises(type(failure)):
            handler.get_connection()
        mock_smtp().close.assert_called_once_with()


class SMTPCollector:
    def __init__(self):
        self.envelopes = []

    async def handle_DATA(self, server, session, envelope):
        self.envelopes.append(envelope)
        return "250 OK"


def test_mail_delivery_over_smtp(logger, local_hostname):
    # Controller.start() confirms the server is up by connecting to the port
    # it was given, so it cannot be asked for whatever happens to be free.
    address = unused_tcp_address()
    collector = SMTPCollector()
    controller = Controller(collector, hostname=address[0], port=address[1])
    try:
        controller.start()
        with (
            logbook.MailHandler(
                "from@example.test",
                ["to@example.test"],
                server_addr=address,
                format_string="Subject: café\n\n{record.message}",
            ),
            logbook.Flags(errors="raise"),
        ):
            logger.error("café 日本語")
    finally:
        controller.stop()

    (envelope,) = collector.envelopes
    assert envelope.mail_from == "from@example.test"
    assert envelope.rcpt_tos == ["to@example.test"]
    message = email.message_from_bytes(envelope.content, policy=email.policy.default)
    assert message["Subject"] == "café"
    assert message.get_content() == "café 日本語"


def test_mail_handler(activation_strategy, logger):
    subject = "\xf8nicode"
    handler = make_fake_mail_handler(subject=subject)
    with capturing_stderr_context() as fallback:
        with activation_strategy(handler):
            logger.warning("This is not mailed")
            try:
                1 / 0  # noqa: B018
            except Exception:
                logger.exception("Viva la Espa\xf1a")

        if not handler.mails:
            # if sending the mail failed, the reason should be on stderr
            assert False, fallback.getvalue()  # noqa: B011

        assert len(handler.mails) == 1
        sender, receivers, mail = handler.mails[0]  # noqa: RUF059
        mail = mail.replace("\r", "")
        assert sender == handler.from_addr
        assert "=?utf-8?q?=C3=B8nicode?=" in mail
        header, data = mail.split("\n\n", 1)
        if "Content-Transfer-Encoding: base64" in header:
            data = base64.b64decode(data).decode("utf-8")
        assert re.search(r"Message type:\s+ERROR", data)
        assert re.search(r"Location:.*%s" % re.escape(__file_without_pyc__), data)  # noqa: UP031
        assert re.search(r"Module:\s+%s" % __name__, data)  # noqa: UP031
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
        logger.warning("Testing")
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
    assert re.search(r"Module:\s+%s" % __name__, body)  # noqa: UP031
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
        logger.warning("Testing")
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

            mock_smtp.assert_called_once_with("server.example.com", 465, timeout=5.0)
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

            mock_smtp.assert_called_once_with("server.example.com", 465, timeout=5.0)
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

            mock_smtp.assert_called_once_with("server.example.com", 587, timeout=5.0)
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

            mock_smtp.assert_called_once_with("server.example.com", 25, timeout=5.0)
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

            mock_smtp.assert_called_once_with("127.0.0.1", 25, timeout=5.0)
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

            mock_smtp.assert_called_once_with("127.0.0.1", 587, timeout=5.0)
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

            mock_smtp.assert_called_once_with("server.example.com", 465, timeout=5.0)
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

            mock_smtp.assert_called_once_with("server.example.com", 465, timeout=5.0)
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

            mock_smtp.assert_called_once_with("server.example.com", 465, timeout=5.0)
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
                "server.example.com", 465, context=ANY, timeout=5.0
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
                "server.example.com", 465, context=None, timeout=5.0
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

            mock_smtp_ssl.assert_called_once_with(
                "127.0.0.1", 465, context=None, timeout=5.0
            )
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
                "server.example.com", 465, context=context, timeout=5.0
            )
            mock_smtp_ssl().starttls.assert_not_called()
            mock_smtp().login.assert_called_once_with("username", "password")
            mock_load_cert_chain.assert_not_called()


def test_mail_handler_timeout_none_disables_the_timeout():
    with patch("smtplib.SMTP", autospec=True) as mock_smtp:
        handler = logbook.MailHandler(
            "from@example.com",
            ["to@example.com"],
            server_addr=("server.example.com", 25),
            timeout=None,
        )
        handler.get_connection()
        mock_smtp.assert_called_once_with("server.example.com", 25, timeout=None)
