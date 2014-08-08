# -*- coding: utf-8 -*-
from .utils import require_py3, capturing_stderr_context

import logbook


@require_py3
def test_default_format_unicode(logger):
    with capturing_stderr_context() as stream:
        logger.warn('\u2603')
    assert 'WARNING: testlogger: \u2603' in stream.getvalue()


@require_py3
def test_default_format_encoded(logger):
    with capturing_stderr_context() as stream:
        # it's a string but it's in the right encoding so don't barf
        logger.warn('\u2603')
    assert 'WARNING: testlogger: \u2603' in stream.getvalue()


@require_py3
def test_default_format_bad_encoding(logger):
    with capturing_stderr_context() as stream:
        # it's a string, is wrong, but just dump it in the logger,
        # don't try to decode/encode it
        logger.warn('Русский'.encode('koi8-r'))
    assert "WARNING: testlogger: b'\\xf2\\xd5\\xd3\\xd3\\xcb\\xc9\\xca'" in stream.getvalue()


@require_py3
def test_custom_unicode_format_unicode(logger):
    format_string = ('[{record.level_name}] '
                     '{record.channel}: {record.message}')
    with capturing_stderr_context() as stream:
        with logbook.StderrHandler(format_string=format_string):
            logger.warn("\u2603")
    assert '[WARNING] testlogger: \u2603' in stream.getvalue()


@require_py3
def test_custom_string_format_unicode(logger):
    format_string = ('[{record.level_name}] '
                     '{record.channel}: {record.message}')
    with capturing_stderr_context() as stream:
        with logbook.StderrHandler(format_string=format_string):
            logger.warn('\u2603')
    assert '[WARNING] testlogger: \u2603' in stream.getvalue()


@require_py3
def test_unicode_message_encoded_params(logger):
    with capturing_stderr_context() as stream:
        logger.warn("\u2603 {0}", "\u2603".encode('utf8'))
    assert "WARNING: testlogger: \u2603 b'\\xe2\\x98\\x83'" in stream.getvalue()


@require_py3
def test_encoded_message_unicode_params(logger):
    with capturing_stderr_context() as stream:
        logger.warn('\u2603 {0}'.encode('utf8'), '\u2603')
    assert 'WARNING: testlogger: \u2603 \u2603' in stream.getvalue()
