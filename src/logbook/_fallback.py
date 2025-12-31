"""
logbook._fallback
~~~~~~~~~~~~~~~~~

Fallback implementations in case speedups is not around.

:copyright: (c) 2010 by Armin Ronacher, Georg Brandl.
:license: BSD, see LICENSE for more details.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextvars import ContextVar
from itertools import chain, count
from typing import Any, Generic, TypeVar

from logbook.helpers import get_iterator_next_method

_missing = object()

T = TypeVar("T")


class group_reflected_property:
    def __init__(self, default, *, fallback=_missing):
        self.default = default
        self.fallback = fallback
        self.prop_name = None
        self.attr_name = None

    def __set_name__(self, owner: type, name: str) -> None:
        self.prop_name = name
        self.attr_name = f"_{name}"

    def __get__(self, instance: Any, owner: type) -> Any:
        if instance is None:
            return self
        if self.attr_name is None:
            raise TypeError("property is not bound to a class")
        rv = getattr(instance, self.attr_name, _missing)
        if rv is not _missing and rv != self.fallback:
            return rv
        if instance.group is None:
            return self.default
        return getattr(instance.group, self.prop_name)

    def __set__(self, instance: Any, value: Any) -> None:
        setattr(instance, self.attr_name, value)

    def __delete__(self, instance: Any) -> None:
        delattr(instance, self.attr_name)


class ApplicationBound:
    def __init__(self, obj):
        self.__obj = obj

    def __enter__(self):
        self.__obj.push_application()
        return self.__obj

    def __exit__(self, exc_type, exc_value, tb):
        self.__obj.pop_application()


class StackedObject:
    """Baseclass for all objects that provide stack manipulation
    operations.
    """

    def push_context(self):
        """Pushes the stacked object to the context stack."""
        raise NotImplementedError()

    def pop_context(self):
        """Pops the stacked object from the context stack."""
        raise NotImplementedError()

    def push_application(self):
        """Pushes the stacked object to the application stack."""
        raise NotImplementedError()

    def pop_application(self):
        """Pops the stacked object from the application stack."""
        raise NotImplementedError()

    def __enter__(self):
        self.push_context()
        return self

    def __exit__(self, exc_type, exc_value, tb):
        self.pop_context()

    def applicationbound(self):
        """Can be used in combination with the `with` statement to
        execute code while the object is bound to the application.
        """
        return ApplicationBound(self)


class _StackState(Generic[T]):
    """The context stack, stored as a linked list.

    Each node holds one pushed object and points at the node below it.
    Pushing creates a new node; popping goes back to the parent. Because
    popping returns to the same node object rather than rebuilding the
    stack, a merge result cached on that node (``merged``) is still there
    if the context pops back to it later. The empty stack is a single
    root node with ``item = parent = None``.
    """

    __slots__ = ("item", "merged", "parent", "size")

    def __init__(
        self, item: tuple[int, T] | None, parent: _StackState[T] | None
    ) -> None:
        self.item = item
        self.parent = parent
        self.size = 0 if parent is None else parent.size + 1
        self.merged: tuple[tuple[tuple[int, T], ...], tuple[T, ...]] | None = None

    def __iter__(self) -> Iterator[tuple[int, T]]:
        items = []
        node = self
        while node.parent is not None:
            assert node.item is not None
            items.append(node.item)
            node = node.parent
        return iter(reversed(items))

    def __repr__(self) -> str:
        return f"<_StackState len={self.size}>"


class ContextStackManager(Generic[T]):
    """Helper class for context objects that manages a stack of
    objects.
    """

    def __init__(self) -> None:
        self._write_lock = threading.Lock()
        # iter_context_objects compares globals with "is". Python reuses
        # one object for every (), so if the stack empties out again later,
        # an old cache built against the earlier empty stack still matches.
        # That is fine: both are empty, so the cached merge is the same.
        self._global: tuple[tuple[int, T], ...] = ()
        # Every context starts from this one root node. Sharing it across
        # threads is safe: nodes never change after creation, except for
        # "merged", which is written in a single assignment.
        self._root: _StackState[T] = _StackState(None, None)
        self._context_stack: ContextVar[_StackState[T]] = ContextVar(
            "stack", default=self._root
        )
        self._stackop: Callable[[], int] = get_iterator_next_method(count())

    def iter_context_objects(self) -> Iterator[T]:
        """Returns an iterator over all objects for the combined
        application and context cache.
        """
        node = self._context_stack.get()
        current_global = self._global

        memo = node.merged
        if memo is not None and memo[0] is current_global:
            return iter(memo[1])

        stack_objects = sorted(chain(current_global, node), reverse=True)
        objects = tuple(x[1] for x in stack_objects)
        node.merged = (current_global, objects)

        # Each node below keeps its own cache, ready for when the context
        # pops back to that depth. But a cache built against an old global
        # stack will never be used again, and it keeps that stack's handlers
        # alive. Clear those out now rather than waiting for the context to
        # unwind. If another thread stores a fresh cache at the same time,
        # either outcome is fine; the worst case is one extra recompute.
        ancestor = node.parent
        while ancestor is not None:
            memo = ancestor.merged
            if memo is not None and memo[0] is not current_global:
                ancestor.merged = None
            ancestor = ancestor.parent

        return iter(objects)

    def push_context(self, obj: T) -> None:
        node = self._context_stack.get()
        self._context_stack.set(_StackState((self._stackop(), obj), node))

    def pop_context(self) -> T:
        node = self._context_stack.get()
        if node.parent is None:
            raise AssertionError("no objects on stack")
        assert node.item is not None
        self._context_stack.set(node.parent)
        return node.item[1]

    def push_application(self, obj: T) -> None:
        with self._write_lock:
            item = (self._stackop(), obj)
            self._global = (*self._global, item)
            # Not needed for correctness (the "is" check would reject it),
            # but the root node lives as long as the manager, and its cache
            # holds the old global stack alive. Clear it now instead of
            # waiting for an iteration on an empty context stack, which may
            # never happen.
            self._root.merged = None

    def pop_application(self) -> T:
        with self._write_lock:
            current = self._global
            if not current:
                raise AssertionError("no objects on application stack")
            self._global = current[:-1]
            # See push_application. Here it matters more: without this,
            # the root's cache would keep the popped handler alive.
            self._root.merged = None
            return current[-1][1]
