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
        foo = speedups_module.group_reflected_property("foo", "default")

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
