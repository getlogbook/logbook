import logbook
import pytest

logbook.StderrHandler().push_application()


@pytest.fixture
def logger():
    return logbook.Logger('testlogger')


@pytest.fixture
def active_handler(request, test_handler, activation_strategy):

    s = activation_strategy(test_handler)
    s.activate()

    @request.addfinalizer
    def deactivate():
        s.deactivate()

    return test_handler


@pytest.fixture
def test_handler():
    return logbook.TestHandler()


class ActivationStrategy(object):

    def __init__(self, handler):
        super(ActivationStrategy, self).__init__()
        self.handler = handler

    def activate(self):
        raise NotImplementedError()  # pragma: no cover

    def deactivate(self):
        raise NotImplementedError()  # pragma: no cover

    def __enter__(self):
        self.activate()
        return self.handler

    def __exit__(self, *_):
        self.deactivate()


class ContextEnteringStrategy(ActivationStrategy):

    def activate(self):
        self.handler.__enter__()

    def deactivate(self):
        self.handler.__exit__(None, None, None)


class PushingStrategy(ActivationStrategy):

    def activate(self):
        from logbook.concurrency import is_gevent_enabled
        if is_gevent_enabled():
            self.handler.push_greenlet()
        else:
            self.handler.push_thread()

    def deactivate(self):
        from logbook.concurrency import is_gevent_enabled
        if is_gevent_enabled():
            self.handler.pop_greenlet()
        else:
            self.handler.pop_thread()


@pytest.fixture(params=[ContextEnteringStrategy, PushingStrategy])
def activation_strategy(request):
    return request.param


@pytest.fixture
def logfile(tmpdir):
    return str(tmpdir.join('logfile.log'))


@pytest.fixture
def default_handler(request):
    returned = logbook.StderrHandler()
    returned.push_application()
    request.addfinalizer(returned.pop_application)
    return returned

try:
    import gevent
except ImportError:
    pass
else:
    @pytest.fixture(scope="module", autouse=True, params=[False, True])
    def gevent(request):
        module_name = getattr(request.module, '__name__', '')
        if (not any(s in module_name for s in ('queues', 'processors'))
                and request.param):
            from logbook.concurrency import enable_gevent, _disable_gevent
            enable_gevent()

            @request.addfinalizer
            def fin():
                _disable_gevent()
