import threading

try:
    import gevent
except ImportError:
    gevent = None


__all__ = (
    "greenlet_get_ident",
    "thread_get_ident",
    "thread_get_name",
)


def thread_get_name():
    return threading.current_thread().name


if gevent is None:
    greenlet_get_ident = threading.get_ident
    thread_get_ident = threading.get_ident
else:
    from gevent.monkey import get_original

    greenlet_get_ident = threading.get_ident
    thread_get_ident = get_original("threading", "get_ident")
