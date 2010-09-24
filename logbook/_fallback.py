# -*- coding: utf-8 -*-
"""
    logbook._fallback
    ~~~~~~~~~~~~~~~~~

    Fallback implementations in case speedups is not around.

    :copyright: (c) 2010 by Armin Ronacher, Georg Brandl.
    :license: BSD, see LICENSE for more details.
"""
import threading
from itertools import count
from thread import get_ident as current_thread


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
        self.push_thread()
        return self

    def __exit__(self, exc_type, exc_value, tb):
        self.pop_thread()

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
        self._context_lock = threading.Lock()
        self._context = threading.local()
        self._cache = {}
        self._stackop = count().next

    def iter_context_objects(self):
        """Returns an iterator over all objects for the combined
        application and context cache.
        """
        tid = current_thread()
        objects = self._cache.get(tid)
        if objects is None:
            if len(self._cache) > _MAX_CONTEXT_OBJECT_CACHE:
                self._cache.clear()
            objects = self._global[:]
            objects.extend(getattr(self._context, 'stack', ()))
            objects.sort(reverse=True)
            objects = [x[1] for x in objects]
            self._cache[tid] = objects
        return iter(objects)

    def push_thread(self, obj):
        self._context_lock.acquire()
        try:
            self._cache.pop(current_thread(), None)
            item = (self._stackop(), obj)
            stack = getattr(self._context, 'stack', None)
            if stack is None:
                self._context.stack = [item]
            else:
                stack.append(item)
        finally:
            self._context_lock.release()

    def pop_thread(self):
        self._context_lock.acquire()
        try:
            self._cache.pop(current_thread(), None)
            stack = getattr(self._context, 'stack', None)
            assert stack, 'no objects on stack'
            return stack.pop()[1]
        finally:
            self._context_lock.release()

    def push_application(self, obj):
        self._global.append((self._stackop(), obj))
        self._cache.clear()

    def pop_application(self):
        assert self._global, 'no objects on application stack'
        popped = self._global.pop()[1]
        self._cache.clear()
        return popped
