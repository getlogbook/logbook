"""
logbook._fallback
~~~~~~~~~~~~~~~~~

Fallback implementations in case speedups is not around.

:copyright: (c) 2010 by Armin Ronacher, Georg Brandl.
:license: BSD, see LICENSE for more details.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextvars import ContextVar
from itertools import chain, count
from typing import Any, Generic, SupportsIndex, TypeVar, overload
from weakref import WeakKeyDictionary

from typing_extensions import TypeAliasType

from logbook.helpers import get_iterator_next_method

_missing = object()
_MAX_CONTEXT_OBJECT_CACHE = 256

T_co = TypeVar("T_co", covariant=True)
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


class FrozenSequence(Sequence[T_co]):
    __slots__ = ("__weakref__", "_hash", "_items")

    def __init__(self, iterable: Iterable[T_co] = ()) -> None:
        self._items = tuple(iterable)
        self._hash: int | None = None

    @overload
    def __getitem__(self, index: SupportsIndex) -> T_co: ...

    @overload
    def __getitem__(self, index: slice) -> FrozenSequence[T_co]: ...

    def __getitem__(self, index: SupportsIndex | slice) -> T_co | FrozenSequence[T_co]:
        if isinstance(index, slice):
            return FrozenSequence(self._items[index])
        return self._items[index]

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[T_co]:
        return iter(self._items)

    def __reversed__(self) -> Iterator[T_co]:
        return reversed(self._items)

    def __contains__(self, item: object) -> bool:
        return item in self._items

    def __eq__(self, other: object) -> bool:
        if isinstance(other, FrozenSequence):
            return self._items == other._items
        return NotImplemented

    def __hash__(self) -> int:
        if self._hash is None:
            self._hash = hash(self._items)
        return self._hash

    def __repr__(self) -> str:
        if self._items:
            items = repr(self._items)
        else:
            items = ""
        return f"{self.__class__.__name__}({items})"


FrozenStack = TypeAliasType(
    "FrozenStack", FrozenSequence[tuple[int, T]], type_params=(T,)
)


class ContextStackManager(Generic[T]):
    """Helper class for context objects that manages a stack of
    objects.
    """

    def __init__(self) -> None:
        self._global: list[T] = []
        self._context_stack: ContextVar[FrozenStack[T]] = ContextVar(
            "stack", default=FrozenSequence()
        )
        self._cache: WeakKeyDictionary[FrozenStack[T], list[T]] = WeakKeyDictionary()
        self._stackop: Callable[[], int] = get_iterator_next_method(count())
        self._lock = threading.Lock()

    def iter_context_objects(self) -> Iterator[T]:
        """Returns an iterator over all objects for the combined
        application and context cache.
        """

        with self._lock:
            stack = self._context_stack.get()
            objects = self._cache.get(stack)
            if objects is None:
                if len(self._cache) >= _MAX_CONTEXT_OBJECT_CACHE:
                    self._cache.clear()
                stack_objects = sorted(
                    chain(
                        self._global,
                        stack,
                    ),
                    reverse=True,
                )
                objects = [x[1] for x in stack_objects]
                self._cache[stack] = objects
        return iter(objects)

    def push_context(self, obj: T) -> None:
        item = (self._stackop(), obj)
        stack = self._context_stack.get()
        self._context_stack.set(FrozenSequence((*stack, item)))

    def pop_context(self) -> T:
        stack = self._context_stack.get()
        assert stack, "no objects on stack"
        *remaining, poppped = stack
        self._context_stack.set(FrozenSequence(remaining))
        return poppped[1]

    def push_application(self, obj: T) -> None:
        item = (self._stackop(), obj)
        with self._lock:
            self._global.append(item)
            self._cache.clear()

    def pop_application(self) -> T:
        with self._lock:
            assert self._global, "no objects on application stack"
            popped = self._global.pop()
            self._cache.clear()
            return popped[1]
