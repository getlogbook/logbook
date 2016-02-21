import pytest
import logbook

from logbook.utils import (
    logged_if_slow, deprecated, forget_deprecation_locations,
    suppressed_deprecations, log_deprecation_message)
from time import sleep

_THRESHOLD = 0.1

try:
    from unittest.mock import Mock, call
except ImportError:
    from mock import Mock, call


def test_logged_if_slow_reached(test_handler):
    with test_handler.applicationbound():
        with logged_if_slow('checking...', threshold=_THRESHOLD):
            sleep(2 * _THRESHOLD)
        assert len(test_handler.records) == 1
        [record] = test_handler.records
        assert record.message == 'checking...'


def test_logged_if_slow_did_not_reached(test_handler):
    with test_handler.applicationbound():
        with logged_if_slow('checking...', threshold=_THRESHOLD):
            sleep(_THRESHOLD / 2)
        assert len(test_handler.records) == 0


def test_logged_if_slow_logger():
    logger = Mock()

    with logged_if_slow('checking...', threshold=_THRESHOLD, logger=logger):
        sleep(2 * _THRESHOLD)

    assert logger.log.call_args == call(logbook.DEBUG, 'checking...')


def test_logged_if_slow_level(test_handler):
    with test_handler.applicationbound():
        with logged_if_slow('checking...', threshold=_THRESHOLD,
                            level=logbook.WARNING):
            sleep(2 * _THRESHOLD)

    assert test_handler.records[0].level == logbook.WARNING


def test_logged_if_slow_deprecated(logger, test_handler):
    with test_handler.applicationbound():
        with logged_if_slow('checking...', threshold=_THRESHOLD,
                            func=logbook.error):
            sleep(2 * _THRESHOLD)

    assert test_handler.records[0].level == logbook.ERROR
    assert test_handler.records[0].message == 'checking...'

    with pytest.raises(TypeError):
        logged_if_slow('checking...', logger=logger, func=logger.error)


def test_deprecated_func_called(capture):
    assert deprecated_func(1, 2) == 3


def test_deprecation_message(capture):
    deprecated_func(1, 2)

    [record] = capture.records
    assert "deprecated" in record.message
    assert 'deprecated_func' in record.message


def test_deprecation_with_message(capture):

    @deprecated("use something else instead")
    def func(a, b):
        return a + b

    func(1, 2)

    [record] = capture.records
    assert "use something else instead" in record.message
    assert "func is deprecated" in record.message


def test_no_deprecations(capture):

    @deprecated('msg')
    def func(a, b):
        return a + b

    with suppressed_deprecations():
        assert func(1, 2) == 3
    assert not capture.records


def _no_decorator(func):
    return func


@pytest.mark.parametrize('decorator', [_no_decorator, classmethod])
def test_class_deprecation(capture, decorator):

    class Bla(object):

        @deprecated('reason')
        @classmethod
        def func(self, a, b):
            assert isinstance(self, Bla)
            return a + b

    assert Bla().func(2, 4) == 6

    [record] = capture.records
    assert 'Bla.func is deprecated' in record.message


def test_deprecations_different_sources(capture):

    def f():
        deprecated_func(1, 2)

    def g():
        deprecated_func(1, 2)

    f()
    g()
    assert len(capture.records) == 2


def test_deprecations_same_sources(capture):

    def f():
        deprecated_func(1, 2)

    f()
    f()
    assert len(capture.records) == 1


def test_deprecation_message_different_sources(capture):

    def f(flag):
        if flag:
            log_deprecation_message('first message type')
        else:
            log_deprecation_message('second message type')

    f(True)
    f(False)
    assert len(capture.records) == 2


def test_deprecation_message_same_sources(capture):

    def f(flag):
        if flag:
            log_deprecation_message('first message type')
        else:
            log_deprecation_message('second message type')

    f(True)
    f(True)
    assert len(capture.records) == 1


def test_deprecation_message_full_warning(capture):
    def f():
        log_deprecation_message('some_message')
    f()

    [record] = capture.records
    assert record.message == 'Deprecation message: some_message'


def test_name_doc():
    @deprecated
    def some_func():
        """docstring here"""
        pass

    assert some_func.__name__ == 'some_func'
    assert 'docstring here' in some_func.__doc__


def test_doc_update():
    @deprecated('some_message')
    def some_func():
        """docstring here"""
        pass

    some_func.__doc__ = 'new_docstring'

    assert 'docstring here' not in some_func.__doc__
    assert 'new_docstring' in some_func.__doc__
    assert 'some_message' in some_func.__doc__


def test_deprecatd_docstring():

    message = "Use something else instead"

    @deprecated()
    def some_func():
        """This is a function
        """

    @deprecated(message)
    def other_func():
        """This is another function
        """

    assert ".. deprecated" in some_func.__doc__
    assert ".. deprecated\n   {0}".format(message) in other_func.__doc__


@pytest.fixture
def capture(request):
    handler = logbook.TestHandler(level=logbook.WARNING)
    handler.push_application()

    @request.addfinalizer
    def pop():
        handler.pop_application()
    return handler


@deprecated
def deprecated_func(a, b):
    return a + b


@pytest.fixture(autouse=True)
def forget_locations():
    forget_deprecation_locations()
