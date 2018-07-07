has_gevent = True
use_gevent = False
try:
    import gevent

    def enable_gevent():
        global use_gevent
        use_gevent = True

    def _disable_gevent():  # for testing
        global use_gevent
        use_gevent = False

    def is_gevent_enabled():
        global use_gevent
        return use_gevent
except ImportError:
    has_gevent = False

    def enable_gevent():
        pass

    def _disable_gevent():
        pass

    def is_gevent_enabled():
        return False


if has_gevent:
    from gevent.monkey import get_original as _get_original
    ThreadLock = _get_original('threading', 'Lock')
    ThreadRLock = _get_original('threading', 'RLock')
    try:
        thread_get_ident = _get_original('threading', 'get_ident')
    except AttributeError:
        # In 2.7, this is called _get_ident
        thread_get_ident = _get_original('threading', '_get_ident')
    thread_local = _get_original('threading', 'local')

    from gevent.thread import get_ident as greenlet_get_ident
    from gevent.local import local as greenlet_local
    from gevent.lock import BoundedSemaphore
    from gevent.threading import __threading__

    def thread_get_name():
        return __threading__.currentThread().getName()

    class GreenletRLock(object):
        def __init__(self):
            self._thread_local = thread_local()
            self._owner = None
            self._wait_queue = []
            self._count = 0

        def __repr__(self):
            owner = self._owner
            return "<%s owner=%r count=%d>" % (self.__class__.__name__, owner,
                                               self._count)

        def acquire(self, blocking=1):
            tid = thread_get_ident()
            gid = greenlet_get_ident()
            tid_gid = (tid, gid)

            # We trust the GIL here so we can do this comparison w/o locking.
            if tid_gid == self._owner:
                self._count += 1
                return True

            greenlet_lock = self._get_greenlet_lock()

            self._wait_queue.append(gid)
            # this is a safety in case an exception is raised somewhere
            # and we must make sure we're not in the queue
            # otherwise it'll get stuck forever.
            remove_from_queue_on_return = True
            try:
                while True:
                    if not greenlet_lock.acquire(blocking):
                        return False  # non-blocking and failed to acquire lock

                    if self._wait_queue[0] == gid:
                        # Hurray, we can have the lock.
                        self._owner = tid_gid
                        self._count = 1

                        # don't remove us from the queue
                        remove_from_queue_on_return = False
                        return True
                    else:
                        # we already hold the greenlet lock so obviously
                        # the owner is not in our thread.
                        greenlet_lock.release()
                        if blocking:
                            # 500 us -> initial delay of 1 ms
                            gevent.sleep(0.0005)
                        else:
                            return False
            finally:
                if remove_from_queue_on_return:
                    self._wait_queue.remove(gid)

        def release(self):
            tid_gid = (thread_get_ident(), greenlet_get_ident())
            if tid_gid != self._owner:
                raise RuntimeError("cannot release un-acquired lock")

            self._count -= 1
            if not self._count:
                self._owner = None
                gid = self._wait_queue.pop(0)
                assert gid == tid_gid[1]
                self._thread_local.greenlet_lock.release()

        __enter__ = acquire

        def __exit__(self, t, v, tb):
            self.release()

        def _get_greenlet_lock(self):
            if not hasattr(self._thread_local, 'greenlet_lock'):
                greenlet_lock = self._thread_local.greenlet_lock = BoundedSemaphore(1)
            else:
                greenlet_lock = self._thread_local.greenlet_lock
            return greenlet_lock

        def _is_owned(self):
            return self._owner == (thread_get_ident(), greenlet_get_ident())
else:
    from threading import (
        Lock as ThreadLock, RLock as ThreadRLock, currentThread)
    try:
        from thread import (
            get_ident as thread_get_ident, _local as thread_local)
    except ImportError:
        from _thread import (
            get_ident as thread_get_ident, _local as thread_local)

    def thread_get_name():
        return currentThread().getName()

    greenlet_get_ident = thread_get_ident

    greenlet_local = thread_local

    class GreenletRLock(object):
        def acquire(self):
            pass

        def release(self):
            pass

        def __enter__(self):
            pass

        def __exit__(self, t, v, tb):
            pass


def new_fine_grained_lock():
    global use_gevent
    if use_gevent:
        return GreenletRLock()
    else:
        return ThreadRLock()


has_contextvars = True
try:
    import contextvars
except ImportError:
    has_contextvars = False

if has_contextvars:
    from contextvars import ContextVar
    from itertools import count

    contextident_counter = count()
    context_ident = ContextVar('context_ident')

    def context_get_ident():
        try:
            return context_ident.get()
        except LookupError:
            ident = 'context-%s' % next(contextident_counter)
            context_ident.set(ident)
            return ident

    def is_context_enabled():
        try:
            context_ident.get()
            return True
        except LookupError:
            return False

else:
    ContextVar = None
    context_get_ident = None

    def is_context_enabled():
        return False
