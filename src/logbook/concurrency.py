import threading
import warnings
from functools import cache

from typing_extensions import deprecated

try:
    import gevent
except ImportError:
    gevent = None


__all__ = (
    "enable_gevent",  # deprecated
    "greenlet_get_ident",
    "is_gevent_enabled",  # deprecated
    "new_fine_grained_lock",  # deprecated
    "thread_get_ident",
    "thread_get_name",
)


_gevent_enabled = False


@deprecated("enable_gevent() is deprecated, use gevent.monkey instead.")
def enable_gevent():
    global _gevent_enabled
    if gevent is not None:
        _gevent_enabled = True


def _disable_gevent():  # for testing
    global _gevent_enabled
    _gevent_enabled = False


@deprecated("is_gevent_enabled() is deprecated")
def is_gevent_enabled():
    return _gevent_enabled


def thread_get_name():
    return threading.current_thread().name


if gevent is None:
    greenlet_get_ident = threading.get_ident
    thread_get_ident = threading.get_ident
else:
    from gevent.monkey import get_original

    greenlet_get_ident = threading.get_ident
    thread_get_ident = get_original("threading", "get_ident")


@cache
def _get_gevent_lock_cls():
    import gevent.lock
    from gevent.monkey import is_module_patched

    if is_module_patched("threading"):
        return threading.RLock
    else:
        warnings.warn(
            (
                "Implicit use of gevent.lock.RLock via logbook.concurrency."
                "enable_gevent() is deprecated. Use gevent.monkey.patch_all() "
                "or gevent.monkey.patch_thread() instead."
            ),
            category=DeprecationWarning,
            stacklevel=2,
        )
        return gevent.lock.RLock


def _new_fine_grained_lock():
    global _gevent_enabled
    if _gevent_enabled:
        lock_cls = _get_gevent_lock_cls()
        return lock_cls()
    else:
        return threading.RLock()


@deprecated("new_fine_grained_lock() is deprecated")
def new_fine_grained_lock():
    return _new_fine_grained_lock()
