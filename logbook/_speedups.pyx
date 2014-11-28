# -*- coding: utf-8 -*-
"""
    logbook._speedups
    ~~~~~~~~~~~~~~~~~

    Cython implementation of some core objects.

    :copyright: (c) 2010 by Armin Ronacher, Georg Brandl.
    :license: BSD, see LICENSE for more details.
"""

import platform
from logbook.concurrency import (is_gevent_enabled, thread_get_ident, greenlet_get_ident, thread_local,
                                 GreenletRLock, greenlet_local)

from cpython.dict cimport PyDict_Clear, PyDict_SetItem
from cpython.list cimport PyList_New, PyList_Append, PyList_Sort, \
     PyList_SET_ITEM, PyList_GET_SIZE
from cpython.pythread cimport PyThread_type_lock, PyThread_allocate_lock, \
     PyThread_release_lock, PyThread_acquire_lock, WAIT_LOCK

cdef object _missing = object()

cdef enum:
    _MAX_CONTEXT_OBJECT_CACHE = 256


cdef class group_reflected_property:
    cdef object name
    cdef object _name
    cdef object default
    cdef object fallback

    def __init__(self, name, object default, object fallback=_missing):
        self.name = name
        self._name = '_' + name
        self.default = default
        self.fallback = fallback

    def __get__(self, obj, type):
        if obj is None:
            return self
        rv = getattr3(obj, self._name, _missing)
        if rv is not _missing and rv != self.fallback:
            return rv
        if obj.group is None:
            return self.default
        return getattr(obj.group, self.name)

    def __set__(self, obj, value):
        setattr(obj, self._name, value)

    def __del__(self, obj):
        delattr(obj, self._name)


cdef class _StackItem:
    cdef int id
    cdef readonly object val

    def __init__(self, int id, object val):
        self.id = id
        self.val = val
    def __richcmp__(_StackItem self, _StackItem other, int op):
        cdef int diff = other.id - self.id # preserving older code
        if op == 0: # <
            return diff < 0
        if op == 1: # <=
            return diff <= 0
        if op == 2: # ==
            return diff == 0
        if op == 3: # !=
            return diff != 0
        if op == 4: # >
            return diff > 0
        if op == 5: # >=
            return diff >= 0
        assert False, "should never get here"

cdef class _StackBound:
    cdef object obj
    cdef object push_func
    cdef object pop_func

    def __init__(self, obj, push, pop):
        self.obj = obj
        self.push_func = push
        self.pop_func = pop

    def __enter__(self):
        self.push_func()
        return self.obj

    def __exit__(self, exc_type, exc_value, tb):
        self.pop_func()


cdef class StackedObject:
    """Baseclass for all objects that provide stack manipulation
    operations.
    """

    cpdef push_greenlet(self):
        """Pushes the stacked object to the greenlet stack."""
        raise NotImplementedError()

    cpdef pop_greenlet(self):
        """Pops the stacked object from the greenlet stack."""
        raise NotImplementedError()

    cpdef push_thread(self):
        """Pushes the stacked object to the thread stack."""
        raise NotImplementedError()

    cpdef pop_thread(self):
        """Pops the stacked object from the thread stack."""
        raise NotImplementedError()

    cpdef push_application(self):
        """Pushes the stacked object to the application stack."""
        raise NotImplementedError()

    cpdef pop_application(self):
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

    cpdef greenletbound(self):
        """Can be used in combination with the `with` statement to
        execute code while the object is bound to the greenlet.
        """
        return _StackBound(self, self.push_greenlet, self.pop_greenlet)

    cpdef threadbound(self):
        """Can be used in combination with the `with` statement to
        execute code while the object is bound to the thread.
        """
        return _StackBound(self, self.push_thread, self.pop_thread)

    cpdef applicationbound(self):
        """Can be used in combination with the `with` statement to
        execute code while the object is bound to the application.
        """
        return _StackBound(self, self.push_application, self.pop_application)


cdef class ContextStackManager:
    cdef list _global
    cdef PyThread_type_lock _thread_context_lock
    cdef object _thread_context
    cdef object _greenlet_context_lock
    cdef object _greenlet_context
    cdef dict _cache
    cdef int _stackcnt

    def __init__(self):
        self._global = []
        self._thread_context_lock = PyThread_allocate_lock()
        self._thread_context = thread_local()
        self._greenlet_context_lock = GreenletRLock()
        self._greenlet_context = greenlet_local()
        self._cache = {}
        self._stackcnt = 0

    cdef _stackop(self):
        self._stackcnt += 1
        return self._stackcnt

    cpdef iter_context_objects(self):
        use_gevent = is_gevent_enabled()
        tid = greenlet_get_ident() if use_gevent else thread_get_ident()
        objects = self._cache.get(tid)
        if objects is None:
            if PyList_GET_SIZE(self._cache) > _MAX_CONTEXT_OBJECT_CACHE:
                PyDict_Clear(self._cache)
            objects = self._global[:]
            objects.extend(getattr3(self._thread_context, 'stack', ()))
            if use_gevent:
                objects.extend(getattr3(self._greenlet_context, 'stack', ()))
            PyList_Sort(objects)
            objects = [(<_StackItem>x).val for x in objects]
            PyDict_SetItem(self._cache, tid, objects)
        return iter(objects)

    cpdef push_greenlet(self, obj):
        self._greenlet_context_lock.acquire()
        try:
            self._cache.pop(greenlet_get_ident(), None)
            item = _StackItem(self._stackop(), obj)
            stack = getattr3(self._greenlet_context, 'stack', None)
            if stack is None:
                self._greenlet_context.stack = [item]
            else:
                PyList_Append(stack, item)
        finally:
            self._greenlet_context_lock.release()

    cpdef pop_greenlet(self):
        self._greenlet_context_lock.acquire()
        try:
            self._cache.pop(greenlet_get_ident(), None)
            stack = getattr3(self._greenlet_context, 'stack', None)
            assert stack, 'no objects on stack'
            return (<_StackItem>stack.pop()).val
        finally:
            self._greenlet_context_lock.release()

    cpdef push_thread(self, obj):
        PyThread_acquire_lock(self._thread_context_lock, WAIT_LOCK)
        try:
            self._cache.pop(thread_get_ident(), None)
            item = _StackItem(self._stackop(), obj)
            stack = getattr3(self._thread_context, 'stack', None)
            if stack is None:
                self._thread_context.stack = [item]
            else:
                PyList_Append(stack, item)
        finally:
            PyThread_release_lock(self._thread_context_lock)

    cpdef pop_thread(self):
        PyThread_acquire_lock(self._thread_context_lock, WAIT_LOCK)
        try:
            self._cache.pop(thread_get_ident(), None)
            stack = getattr3(self._thread_context, 'stack', None)
            assert stack, 'no objects on stack'
            return (<_StackItem>stack.pop()).val
        finally:
            PyThread_release_lock(self._thread_context_lock)

    cpdef push_application(self, obj):
        self._global.append(_StackItem(self._stackop(), obj))
        PyDict_Clear(self._cache)

    cpdef pop_application(self):
        assert self._global, 'no objects on application stack'
        popped = (<_StackItem>self._global.pop()).val
        PyDict_Clear(self._cache)
        return popped
