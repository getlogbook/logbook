import importlib

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

    class A:
        foo = speedups_module.group_reflected_property("default")

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


def test_frozen_sequence(speedups_module):
    items = [1, 2, 3]
    seq = speedups_module.FrozenSequence(iter(items))
    assert list(seq) == items
    seq = speedups_module.FrozenSequence(items)
    assert list(seq) == items
    assert len(seq) == 3
    assert list(reversed(seq)) == [3, 2, 1]
    assert 1 in seq
    assert seq[0] == 1
    assert seq[1:] == speedups_module.FrozenSequence([2, 3])
    assert repr(seq) == "FrozenSequence((1, 2, 3))"
    assert repr(speedups_module.FrozenSequence()) == "FrozenSequence()"
