import threading
from logbook import debug as logbook_debug


class _SlowContextNotifier(object):

    def __init__(self, threshold, logger_func, args, kwargs):
        self.logger_func = logger_func
        self.args = args
        self.kwargs = kwargs or {}
        self.evt = threading.Event()
        self.threshold = threshold
        self.thread = threading.Thread(target=self._notifier)

    def _notifier(self):
        if not self.evt.wait(timeout=self.threshold):
            self.logger_func(*self.args, **self.kwargs)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.evt.set()
        self.thread.join()


def log_if_slow_context(message, threshold=1, func=logbook_debug, args=None, kwargs=None):
    full_args = (message, ) if args is None else (message, ) + args
    return _SlowContextNotifier(threshold, func, full_args, kwargs)
