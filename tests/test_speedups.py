import gc
import importlib
import sys
import threading
import weakref
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from contextvars import ContextVar, copy_context
from threading import Barrier

import pytest

_GIL_ENABLED = getattr(sys, "_is_gil_enabled", lambda: True)()


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


def test_group_reflected_property_unbound(speedups_module):
    # The descriptor learns which attribute to use via __set_name__, which
    # only runs when it is assigned inside a class body. One created
    # without that step has no attribute name to work with.
    class A:
        group = None

    descriptor = speedups_module.group_reflected_property("default")
    instance = A()

    with pytest.raises(TypeError):
        descriptor.__get__(instance, A)
    with pytest.raises(TypeError):
        descriptor.__set__(instance, "value")
    with pytest.raises(TypeError):
        descriptor.__delete__(instance)


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

    class ContextObject(StackedObject):
        def push_context(self):
            pass

        def pop_context(self):
            pass

        def push_application(self):
            pass

        def pop_application(self):
            pass

    c = ContextObject()

    # https://github.com/getlogbook/logbook/issues/500
    with pytest.raises(SystemExit):
        with c:
            raise SystemExit
    with pytest.raises(SystemExit):
        with c.applicationbound():
            raise SystemExit


def test_context_stack_manager(speedups_module):
    class StackObject:
        def __init__(self, i):
            self.i = i

        def __repr__(self):
            return f"StackObject({self.i})"

    ContextStackManager = speedups_module.ContextStackManager
    stack_manager = ContextStackManager()

    assert len(stack_manager._global) == 0
    assert type(stack_manager._context_stack) is ContextVar

    num_objects = 256
    objects = [StackObject(i) for i in range(num_objects)]

    for obj in objects:
        stack_manager.push_context(obj)
        list(stack_manager.iter_context_objects())

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

    for ctx, cm in reversed(context_managers):
        ctx.run(cm.__exit__, None, None, None)


def test_context_stack_manager_stack_state_repr(speedups_module):
    ContextStackManager = speedups_module.ContextStackManager
    stack_manager = ContextStackManager()

    assert repr(stack_manager._context_stack.get()) == "<_StackState len=0>"

    first = object()
    second = object()
    stack_manager.push_context(first)
    stack_manager.push_context(second)
    assert repr(stack_manager._context_stack.get()) == "<_StackState len=2>"

    assert stack_manager.pop_context() is second
    assert stack_manager.pop_context() is first


def test_context_stack_manager_repeated_iteration(speedups_module):
    ContextStackManager = speedups_module.ContextStackManager
    stack_manager = ContextStackManager()

    handler = object()
    stack_manager.push_context(handler)

    first = list(stack_manager.iter_context_objects())
    second = list(stack_manager.iter_context_objects())
    assert first == [handler]
    assert second == first


def test_context_stack_manager_global_change_invalidates_cache(speedups_module):
    ContextStackManager = speedups_module.ContextStackManager
    stack_manager = ContextStackManager()

    local = object()
    first_global = object()
    second_global = object()

    stack_manager.push_application(first_global)
    stack_manager.push_context(local)
    assert list(stack_manager.iter_context_objects()) == [local, first_global]

    stack_manager.push_application(second_global)
    assert list(stack_manager.iter_context_objects()) == [
        second_global,
        local,
        first_global,
    ]

    assert stack_manager.pop_application() is second_global
    assert list(stack_manager.iter_context_objects()) == [local, first_global]


def test_context_stack_manager_interleaved_push_order(speedups_module):
    # Iteration order depends only on when each object was pushed, not on
    # which of the two stacks it was pushed to.
    ContextStackManager = speedups_module.ContextStackManager
    stack_manager = ContextStackManager()

    first_global = object()
    local = object()
    second_global = object()

    stack_manager.push_application(first_global)
    stack_manager.push_context(local)
    stack_manager.push_application(second_global)
    assert list(stack_manager.iter_context_objects()) == [
        second_global,
        local,
        first_global,
    ]


def test_context_stack_manager_pop_restores_cached_state(speedups_module):
    ContextStackManager = speedups_module.ContextStackManager
    stack_manager = ContextStackManager()

    outer = object()
    inner = object()

    stack_manager.push_context(outer)
    assert list(stack_manager.iter_context_objects()) == [outer]

    for _ in range(3):
        stack_manager.push_context(inner)
        assert list(stack_manager.iter_context_objects()) == [inner, outer]
        assert stack_manager.pop_context() is inner
        assert list(stack_manager.iter_context_objects()) == [outer]

    assert stack_manager.pop_context() is outer
    assert list(stack_manager.iter_context_objects()) == []


def test_context_stack_manager_application_stack_churn(speedups_module):
    # A cached merge is reused only if the application stack is still the
    # exact same object it was built from. That check is only safe because
    # the cache keeps the old stack alive; if it compared by memory address
    # alone, a freed stack's address could be reused by a new one and a
    # stale result served. Churning the application stack makes such a bug
    # show up within a few rounds.
    ContextStackManager = speedups_module.ContextStackManager
    stack_manager = ContextStackManager()

    local = object()
    stack_manager.push_application(object())
    stack_manager.push_context(local)
    assert len(list(stack_manager.iter_context_objects())) == 2

    for _ in range(100):
        stack_manager.pop_application()
        handler = object()
        stack_manager.push_application(handler)
        assert list(stack_manager.iter_context_objects()) == [handler, local]


def test_context_stack_manager_pop_application_releases_handler(speedups_module):
    # The root node lives as long as the manager, so a handler popped off
    # the application stack must not be kept alive by the root's cached
    # merge.
    class Handler:
        pass

    ContextStackManager = speedups_module.ContextStackManager
    stack_manager = ContextStackManager()

    handler = Handler()
    handler_ref = weakref.ref(handler)
    stack_manager.push_application(handler)
    assert list(stack_manager.iter_context_objects()) == [handler]
    assert stack_manager.pop_application() is handler

    del handler
    gc.collect()
    assert handler_ref() is None


def test_context_stack_manager_nested_memos_release_popped_handler(speedups_module):
    # Every node in the context stack can hold a cached merge, and each
    # cache keeps the application handlers it saw alive. After a handler
    # is popped, the next iteration must clear those outdated caches so
    # the handler can be freed before the context stack unwinds.
    class Handler:
        pass

    ContextStackManager = speedups_module.ContextStackManager
    stack_manager = ContextStackManager()

    handler = Handler()
    handler_ref = weakref.ref(handler)
    stack_manager.push_application(handler)

    outer = object()
    inner = object()
    stack_manager.push_context(outer)
    assert list(stack_manager.iter_context_objects()) == [outer, handler]
    stack_manager.push_context(inner)
    assert list(stack_manager.iter_context_objects()) == [inner, outer, handler]

    assert stack_manager.pop_application() is handler
    del handler
    assert list(stack_manager.iter_context_objects()) == [inner, outer]

    gc.collect()
    assert handler_ref() is None

    assert stack_manager.pop_context() is inner
    assert stack_manager.pop_context() is outer


def test_context_stack_manager_contexts_have_independent_caches(speedups_module):
    ContextStackManager = speedups_module.ContextStackManager
    stack_manager = ContextStackManager()

    ctx_one = copy_context()
    ctx_two = copy_context()
    obj_one = object()
    obj_two = object()

    def use_object(obj):
        stack_manager.push_context(obj)
        try:
            return list(stack_manager.iter_context_objects())
        finally:
            assert stack_manager.pop_context() is obj

    values_one = ctx_one.run(use_object, obj_one)
    values_two = ctx_two.run(use_object, obj_two)

    assert values_one == [obj_one]
    assert values_two == [obj_two]
    assert list(stack_manager.iter_context_objects()) == []


def test_context_stack_manager_copied_context_updates_do_not_mutate_parent_cache(
    speedups_module,
):
    ContextStackManager = speedups_module.ContextStackManager
    stack_manager = ContextStackManager()

    parent_obj = object()
    child_obj = object()

    stack_manager.push_context(parent_obj)
    try:
        assert list(stack_manager.iter_context_objects()) == [parent_obj]

        child_ctx = copy_context()

        def mutate_child():
            stack_manager.push_context(child_obj)
            try:
                assert list(stack_manager.iter_context_objects()) == [
                    child_obj,
                    parent_obj,
                ]
            finally:
                assert stack_manager.pop_context() is child_obj

        child_ctx.run(mutate_child)

        assert list(stack_manager.iter_context_objects()) == [parent_obj]
    finally:
        assert stack_manager.pop_context() is parent_obj


def test_context_stack_manager_deep_stack(speedups_module):
    ContextStackManager = speedups_module.ContextStackManager
    stack_manager = ContextStackManager()

    depth = 10_000
    objects = [object() for _ in range(depth)]
    for obj in objects:
        stack_manager.push_context(obj)

    assert list(stack_manager.iter_context_objects()) == objects[::-1]

    for obj in reversed(objects):
        assert stack_manager.pop_context() is obj
    assert list(stack_manager.iter_context_objects()) == []

    # Dropping the context frees the whole 10k-node stack in one go. Each
    # node freeing its parent recursively would use one C stack frame per
    # node and overflow.
    def build_and_drop():
        ctx = copy_context()

        def build():
            for obj in objects:
                stack_manager.push_context(obj)

        ctx.run(build)
        del ctx

    if speedups_module.__name__.endswith("._speedups"):
        # A default (8 MiB) thread stack is deep enough that even recursive
        # freeing of 10k nodes would pass, so run the teardown on a thread
        # with a small stack to make the bug visible. The fallback keeps
        # the default stack: freeing a 10k-node chain of Python objects on
        # a small stack crashes inside CPython itself, whatever we do.
        old_stack_size = threading.stack_size(256 * 1024)
        try:
            thread = threading.Thread(target=build_and_drop)
            thread.start()
            thread.join()
        finally:
            threading.stack_size(old_stack_size)
    else:
        build_and_drop()


def test_context_stack_manager_copied_context_cache_is_thread_safe(speedups_module):
    ContextStackManager = speedups_module.ContextStackManager
    stack_manager = ContextStackManager()

    local = object()
    application = object()
    stack_manager.push_context(local)
    try:
        assert list(stack_manager.iter_context_objects()) == [local]
        contexts = [copy_context() for _ in range(4)]
        barrier = Barrier(len(contexts) + 1)
        iterations = 2_000 if not _GIL_ENABLED else 200

        def read_from_context(ctx):
            def read():
                barrier.wait(timeout=30)
                for _ in range(iterations):
                    objects = list(stack_manager.iter_context_objects())
                    assert objects[-1] is local
                    assert len(objects) in (1, 2)

            ctx.run(read)

        def update_application_stack():
            barrier.wait(timeout=30)
            for _ in range(iterations):
                stack_manager.push_application(application)
                assert stack_manager.pop_application() is application

        with ThreadPoolExecutor(max_workers=len(contexts) + 1) as executor:
            futures = [executor.submit(read_from_context, ctx) for ctx in contexts]
            futures.append(executor.submit(update_application_stack))
            for future in futures:
                future.result()

        # The writer has finished and the application stack is empty again,
        # so every context must now see just [local]. If the race left a
        # bad cached merge behind, the popped application handler would
        # still show up here.
        for ctx in contexts:
            assert ctx.run(lambda: list(stack_manager.iter_context_objects())) == [
                local
            ]
    finally:
        assert stack_manager.pop_context() is local


def test_context_stack_manager_concurrent_application_push_order(speedups_module):
    ContextStackManager = speedups_module.ContextStackManager
    stack_manager = ContextStackManager()

    worker_count = 8
    rounds = 200 if not _GIL_ENABLED else 20
    start = Barrier(worker_count + 1)
    pushed = Barrier(worker_count + 1)
    objects = [object() for _ in range(worker_count)]

    def push_application(obj):
        for _ in range(rounds):
            start.wait(timeout=30)
            stack_manager.push_application(obj)
            pushed.wait(timeout=30)

    failures = []
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [executor.submit(push_application, obj) for obj in objects]

        for _ in range(rounds):
            start.wait(timeout=30)
            pushed.wait(timeout=30)

            snapshot = list(stack_manager._global)
            sequence_numbers = [seq for seq, _obj in snapshot]
            if sequence_numbers != sorted(sequence_numbers):
                failures.append(f"application stack is not sorted: {sequence_numbers}")

            visible = list(stack_manager.iter_context_objects())
            popped = [stack_manager.pop_application() for _ in range(worker_count)]
            if popped != visible:
                failures.append("iteration and popping disagree about stack order")

        for future in futures:
            future.result()

    assert not failures, failures[0]


def test_context_stack_manager_pop_errors(speedups_module):
    ContextStackManager = speedups_module.ContextStackManager
    stack_manager = ContextStackManager()

    with pytest.raises(AssertionError):
        stack_manager.pop_context()

    with pytest.raises(AssertionError):
        stack_manager.pop_application()
