# -*- coding: utf-8 -*-
"""
    logbook._fallback
    ~~~~~~~~~~~~~~~~~

    Fallback implementations in case speedups is not around.

    :copyright: (c) 2010 by Armin Ronacher, Georg Brandl.
    :license: BSD, see LICENSE for more details.
"""
from itertools import count
from logbook.helpers import get_iterator_next_method
from logbook.concurrency import (
    thread_get_ident, greenlet_get_ident, thread_local, greenlet_local,
    ThreadLock, GreenletRLock, is_gevent_enabled, ContextVar, context_get_ident,
    is_context_enabled)

_missing = object()
_MAX_CONTEXT_OBJECT_CACHE = 256


def group_reflected_property(name, default, fallback=_missing):
    """Returns a property for a given name that falls back to the
    value of the group if set.  If there is no such group, the
    provided default is used.
    """
    def _get(self):
        rv = getattr(self, '_' + name, _missing)
        if rv is not _missing and rv != fallback:
            return rv
        if self.group is None:
            return default
        return getattr(self.group, name)

    def _set(self, value):
        setattr(self, '_' + name, value)

    def _del(self):
        delattr(self, '_' + name)
    return property(_get, _set, _del)


class _StackBound(object):

    def __init__(self, obj, push, pop):
        self.__obj = obj
        self.__push = push
        self.__pop = pop

    def __enter__(self):
        self.__push()
        return self.__obj

    def __exit__(self, exc_type, exc_value, tb):
        self.__pop()


class StackedObject(object):
    """Baseclass for all objects that provide stack manipulation
    operations.
    """

    def push_greenlet(self):
        """Pushes the stacked object to the greenlet stack."""
        raise NotImplementedError()

    def pop_greenlet(self):
        """Pops the stacked object from the greenlet stack."""
        raise NotImplementedError()

    def push_context(self):
        """Pushes the stacked object to the context stack."""
        raise NotImplementedError()

    def pop_context(self):
        """Pops the stacked object from the context stack."""
        raise NotImplementedError()

    def push_thread(self):
        """Pushes the stacked object to the thread stack."""
        raise NotImplementedError()

    def pop_thread(self):
        """Pops the stacked object from the thread stack."""
        raise NotImplementedError()

    def push_application(self):
        """Pushes the stacked object to the application stack."""
        raise NotImplementedError()

    def pop_application(self):
        """Pops the stacked object from the application stack."""
        raise NotImplementedError()

    def __enter__(self):
        if is_gevent_enabled():
            self.push_greenlet()
        else:
            self.push_thread()
        return self

    def __exit__(self, exc_type, exc_value, tb):
        if is_gevent_enabled():
            self.pop_greenlet()
        else:
            self.pop_thread()

    def greenletbound(self, _cls=_StackBound):
        """Can be used in combination with the `with` statement to
        execute code while the object is bound to the greenlet.
        """
        return _cls(self, self.push_greenlet, self.pop_greenlet)

    def contextbound(self, _cls=_StackBound):
        """Can be used in combination with the `with` statement to
        execute code while the object is bound to the concurrent
        context.
        """
        return _cls(self, self.push_context, self.pop_context)

    def threadbound(self, _cls=_StackBound):
        """Can be used in combination with the `with` statement to
        execute code while the object is bound to the thread.
        """
        return _cls(self, self.push_thread, self.pop_thread)

    def applicationbound(self, _cls=_StackBound):
        """Can be used in combination with the `with` statement to
        execute code while the object is bound to the application.
        """
        return _cls(self, self.push_application, self.pop_application)


class ContextStackManager(object):
    """Helper class for context objects that manages a stack of
    objects.
    """

    def __init__(self):
        self._global = []
        self._thread_context_lock = ThreadLock()
        self._thread_context = thread_local()
        self._greenlet_context_lock = GreenletRLock()
        self._greenlet_context = greenlet_local()
        self._context_stack = ContextVar('stack')
        self._cache = {}
        self._stackop = get_iterator_next_method(count())

    def iter_context_objects(self):
        """Returns an iterator over all objects for the combined
        application and context cache.
        """
        use_gevent = is_gevent_enabled()
        use_context = is_context_enabled()

        if use_gevent:
            tid = greenlet_get_ident()
        elif use_context:
            tid = context_get_ident()
        else:
            tid = thread_get_ident()

        objects = self._cache.get(tid)
        if objects is None:
            if len(self._cache) > _MAX_CONTEXT_OBJECT_CACHE:
                self._cache.clear()
            objects = self._global[:]
            objects.extend(getattr(self._thread_context, 'stack', ()))

            if use_gevent:
                objects.extend(getattr(self._greenlet_context, 'stack', ()))

            if use_context:
                objects.extend(self._context_stack.get([]))

            objects.sort(reverse=True)
            objects = [x[1] for x in objects]
            self._cache[tid] = objects
        return iter(objects)

    def push_greenlet(self, obj):
        self._greenlet_context_lock.acquire()
        try:
            # remote chance to conflict with thread ids
            self._cache.pop(greenlet_get_ident(), None)
            item = (self._stackop(), obj)
            stack = getattr(self._greenlet_context, 'stack', None)
            if stack is None:
                self._greenlet_context.stack = [item]
            else:
                stack.append(item)
        finally:
            self._greenlet_context_lock.release()

    def pop_greenlet(self):
        self._greenlet_context_lock.acquire()
        try:
            # remote chance to conflict with thread ids
            self._cache.pop(greenlet_get_ident(), None)
            stack = getattr(self._greenlet_context, 'stack', None)
            assert stack, 'no objects on stack'
            return stack.pop()[1]
        finally:
            self._greenlet_context_lock.release()

    def push_context(self, obj):
        self._cache.pop(context_get_ident(), None)
        item = (self._stackop(), obj)
        stack = self._context_stack.get(None)
        if stack is None:
            stack = [item]
            self._context_stack.set(stack)
        else:
            stack.append(item)

    def pop_context(self):
        self._cache.pop(context_get_ident(), None)
        stack = self._context_stack.get(None)
        assert stack, 'no objects on stack'
        return stack.pop()[1]

    def push_thread(self, obj):
        self._thread_context_lock.acquire()
        try:
            self._cache.pop(thread_get_ident(), None)
            item = (self._stackop(), obj)
            stack = getattr(self._thread_context, 'stack', None)
            if stack is None:
                self._thread_context.stack = [item]
            else:
                stack.append(item)
        finally:
            self._thread_context_lock.release()

    def pop_thread(self):
        self._thread_context_lock.acquire()
        try:
            self._cache.pop(thread_get_ident(), None)
            stack = getattr(self._thread_context, 'stack', None)
            assert stack, 'no objects on stack'
            return stack.pop()[1]
        finally:
            self._thread_context_lock.release()

    def push_application(self, obj):
        self._global.append((self._stackop(), obj))
        self._cache.clear()

    def pop_application(self):
        assert self._global, 'no objects on application stack'
        popped = self._global.pop()[1]
        self._cache.clear()
        return popped
