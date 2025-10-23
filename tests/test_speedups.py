import importlib
from contextlib import contextmanager
from contextvars import ContextVar, copy_context
from weakref import WeakKeyDictionary

import pytest


@pytest.fixture(params=["speedups", "fallback"])
def speedups_module(request):
    mod_name = f"logbook._{request.param}"
    try:
        return importlib.import_module(mod_name)
    except ImportError:
        pytest.skip(f"{mod_name} is not available")


def test_group_reflected_property(speedups_module):
    class Group:
        foo = "group"

    descriptor = speedups_module.group_reflected_property("default")

    class A:
        foo = descriptor

        def __init__(self, group=None):
            self.group = group

    a = A()
    assert a.foo == "default"
    a.group = Group()
    assert a.foo == "group"
    a.foo = "set"
    assert a.foo == "set"
    del a.foo
    assert a.foo == "group"

    assert A.foo is descriptor


def test_frozen_sequence(speedups_module):
    FrozenSequence = speedups_module.FrozenSequence
    items = [1, 2, 3]
    seq = FrozenSequence(iter(items))
    assert list(seq) == items
    seq = FrozenSequence(items)
    assert list(seq) == items
    assert len(seq) == 3
    assert list(reversed(seq)) == [3, 2, 1]
    assert 1 in seq
    assert seq[0] == 1
    assert seq[1:] == FrozenSequence([2, 3])
    assert repr(seq) == "FrozenSequence((1, 2, 3))"
    assert repr(FrozenSequence()) == "FrozenSequence()"


def test_stacked_object(speedups_module):
    StackedObject = speedups_module.StackedObject
    s = StackedObject()
    with pytest.raises(NotImplementedError):
        s.push_context()
    with pytest.raises(NotImplementedError):
        s.pop_context()
    with pytest.raises(NotImplementedError):
        s.push_application()
    with pytest.raises(NotImplementedError):
        s.pop_application()


def test_context_stack_manager(speedups_module):
    class StackObject:
        def __init__(self, i):
            self.i = i

        def __repr__(self):
            return f"StackObject({self.i})"

    ContextStackManager = speedups_module.ContextStackManager
    _MAX_CONTEXT_OBJECT_CACHE = speedups_module._MAX_CONTEXT_OBJECT_CACHE
    stack_manager = ContextStackManager()
    assert stack_manager._global == []
    assert type(stack_manager._context_stack) is ContextVar
    assert type(stack_manager._cache) is WeakKeyDictionary

    objects = [StackObject(i) for i in range(_MAX_CONTEXT_OBJECT_CACHE)]

    assert len(stack_manager._cache) == 0
    for obj in objects:
        stack_manager.push_context(obj)
        stack_manager.iter_context_objects()
        # Cache should not grow if there aren't new contexts
        assert len(stack_manager._cache) == 1

    for obj in reversed(objects):
        assert stack_manager.pop_context() is obj

    @contextmanager
    def x(obj, i):
        nonlocal ctx
        stack_manager.push_context(obj)
        current = list(stack_manager.iter_context_objects())
        assert len(current) == i + 1
        ctx = copy_context()
        yield None
        current = list(stack_manager.iter_context_objects())
        assert len(current) == i + 1
        assert stack_manager.pop_context() is obj

    stack_manager = ContextStackManager()
    context_managers = []
    ctx = copy_context()
    for i, obj in enumerate(objects):
        cm = x(obj, i)
        context_managers.append((ctx, cm))
        ctx.run(cm.__enter__)
        assert len(stack_manager._cache) == i + 1

    for ctx, cm in reversed(context_managers):
        ctx.run(cm.__exit__, None, None, None)

    stack_manager = ContextStackManager()
    context_managers = []
    ctx = copy_context()
    for i, obj in enumerate(objects):
        cm = x(obj, i)
        context_managers.append((ctx, cm))
        ctx.run(cm.__enter__)
        assert len(stack_manager._cache) == i + 1

    # Now that the cache is full, it should be cleared after the next iteration
    cm = x(StackObject(len(objects)), len(objects))
    context_managers.append((ctx, cm))
    ctx.run(cm.__enter__)
    assert len(stack_manager._cache) == 1

    for ctx, cm in reversed(context_managers):
        ctx.run(cm.__exit__, None, None, None)
