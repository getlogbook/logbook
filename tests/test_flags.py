import logbook

import pytest

from .utils import capturing_stderr_context


def test_error_flag(logger):
    with capturing_stderr_context() as captured:
        with logbook.Flags(errors='print'):
            with logbook.Flags(errors='silent'):
                logger.warn('Foo {42}', 'aha')
        assert captured.getvalue() == ''

        with logbook.Flags(errors='silent'):
            with logbook.Flags(errors='print'):
                logger.warn('Foo {42}', 'aha')
        assert captured.getvalue() != ''

        with pytest.raises(Exception) as caught:
            with logbook.Flags(errors='raise'):
                logger.warn('Foo {42}', 'aha')
        assert 'Could not format message with provided arguments' in str(
            caught.value)


def test_disable_introspection(logger):
    with logbook.Flags(introspection=False):
        with logbook.TestHandler() as h:
            logger.warn('Testing')
            assert h.records[0].frame is None
            assert h.records[0].calling_frame is None
            assert h.records[0].module is None
