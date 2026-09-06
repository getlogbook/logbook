import pickle

import pytest

import logbook


class SlottedLogger(logbook.Logger):
    __slots__ = ("__private", "tag", "unset")

    def set_private(self, value):
        self.__private = value

    def get_private(self):
        return self.__private


class ChildSlottedLogger(SlottedLogger):
    __slots__ = "child_tag"


@pytest.mark.parametrize("protocol", range(pickle.HIGHEST_PROTOCOL + 1))
@pytest.mark.parametrize("logged", [False, True])
def test_logger_pickle_preserves_dictionary_state(protocol, logged):
    logger = logbook.Logger("test", level=logbook.WARNING)
    logger.tag = "preserved"
    if logged:
        with logbook.NullHandler():
            logger.warning("initialize cached weak reference")
    original_ref = logger._self_ref

    state = logger.__getstate__()
    assert isinstance(state, dict)
    assert state is not logger.__dict__
    assert "_self_ref" not in state
    restored = pickle.loads(pickle.dumps(logger, protocol))
    assert logger._self_ref is original_ref
    if logged:
        assert original_ref() is logger
    assert restored.name == "test"
    assert restored.level == logbook.WARNING
    assert restored.tag == "preserved"
    assert restored._self_ref is None
    with logbook.TestHandler() as handler:
        restored.warning("after pickle")
    assert handler.records[0].dispatcher is restored


@pytest.mark.parametrize("protocol", range(pickle.HIGHEST_PROTOCOL + 1))
def test_logger_pickle_preserves_empty_state(protocol):
    logger = logbook.Logger.__new__(logbook.Logger)
    if hasattr(object, "__getstate__"):
        assert logger.__getstate__() is None
    else:
        assert logger.__getstate__() == {}
    restored = pickle.loads(pickle.dumps(logger, protocol))
    assert type(restored) is logbook.Logger
    assert restored.__dict__ == {}
    assert logger.__dict__ == {}


@pytest.mark.parametrize("protocol", range(pickle.HIGHEST_PROTOCOL + 1))
@pytest.mark.parametrize("logged", [False, True])
def test_logger_pickle_preserves_inherited_slots(protocol, logged):
    logger = ChildSlottedLogger("test")
    logger.tag = "parent"
    logger.child_tag = "child"
    logger.set_private("private")
    if logged:
        with logbook.NullHandler():
            logger.info("initialize cached weak reference")
        assert logger._self_ref() is logger
    restored = pickle.loads(pickle.dumps(logger, protocol))
    assert restored.name == "test"
    assert restored.tag == "parent"
    assert restored.child_tag == "child"
    assert restored.get_private() == "private"
    assert not hasattr(restored, "unset")
    assert restored._self_ref is None
    with logbook.TestHandler() as handler:
        restored.info("after pickle")
    assert handler.records[0].dispatcher is restored
