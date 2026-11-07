import copy
import json
from types import MappingProxyType

import pytest

import logbook


class CustomHandler(logbook.TestHandler):
    pass


@pytest.mark.parametrize("application", [False, True])
def test_from_dict_dispatch_order_and_scope(application, logger):
    config = {
        "objects": [
            {"class": "logbook.NullHandler"},
            {"class": "logbook.TestHandler", "level": "WARNING"},
            {
                "class": f"{__name__}.CustomHandler",
                "level": "ERROR",
                "bubble": True,
            },
        ]
    }
    original = copy.deepcopy(config)
    setup = logbook.NestedSetup.from_dict(config)
    assert config == original
    assert isinstance(setup.objects[2], CustomHandler)
    outer = logbook.TestHandler()
    with outer:
        logger.warning("before")
        with setup.applicationbound() if application else setup:
            logger.info("discarded")
            logger.warning("warning")
            logger.error("error")
        logger.warning("after")
    assert [record.message for record in outer.records] == ["before", "after"]
    assert [record.message for record in setup.objects[1].records] == [
        "warning",
        "error",
    ]
    assert [record.message for record in setup.objects[2].records] == ["error"]


def test_from_dict_processors_flags_and_python_values(logger):
    def add_extra(record):
        record.extra["configured"] = True

    def only_configured(record, handler):
        return record.extra.get("configured", False)

    config = MappingProxyType(
        {
            "objects": (
                MappingProxyType(
                    {"class": logbook.TestHandler, "filter": only_configured}
                ),
                {"class": "logbook.Processor", "callback": add_extra},
                {"class": "logbook.Flags", "errors": "raise"},
            )
        }
    )
    setup = logbook.NestedSetup.from_dict(config)
    handler, processor, flags = setup.objects
    assert handler.filter is only_configured
    assert processor.callback is add_extra
    with setup:
        assert logbook.Flags.get_flag("errors") == "raise"
        logger.info("configured")
    assert handler.records[0].extra["configured"] is True
    assert processor not in logbook.Processor.stack_manager.iter_context_objects()
    assert flags not in logbook.Flags.stack_manager.iter_context_objects()


def test_from_dict_json_file(tmp_path, logger):
    logfile = tmp_path / "events.log"
    configfile = tmp_path / "logging.json"
    configfile.write_text(
        json.dumps(
            {
                "objects": [
                    {
                        "class": "logbook.FileHandler",
                        "filename": str(logfile),
                        "level": "WARNING",
                        "format_string": "{record.message}",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with configfile.open(encoding="utf-8") as stream:
        setup = logbook.NestedSetup.from_dict(json.load(stream))
    try:
        with setup:
            logger.info("discarded")
            logger.warning("caf\u00e9")
        assert logfile.read_text(encoding="utf-8") == "caf\u00e9\n"
    finally:
        setup.objects[0].close()


@pytest.mark.parametrize("config", [{}, {"objects": []}])
def test_from_dict_empty_and_subclass(config):
    class Setup(logbook.NestedSetup):
        pass

    setup = Setup.from_dict(config)
    assert isinstance(setup, Setup)
    assert setup.objects == []


@pytest.mark.parametrize(
    ("config", "error", "message"),
    [
        ([], TypeError, "config must be a mapping"),
        ({"handlers": []}, ValueError, "unknown configuration key"),
        ({"objects": {}}, TypeError, "objects must be a list or tuple"),
        ({"objects": "logbook.NullHandler"}, TypeError, "objects must be"),
        ({"objects": [None]}, TypeError, r"objects\[0\] must be a mapping"),
        ({"objects": [{}]}, ValueError, "missing 'class'"),
        (
            {"objects": [{"class": "NullHandler"}]},
            ValueError,
            "fully qualified name",
        ),
        (
            {"objects": [{"class": "logbook."}]},
            ValueError,
            "fully qualified name",
        ),
        (
            {"objects": [{"class": ".NullHandler"}]},
            ValueError,
            "fully qualified name",
        ),
        ({"objects": [{"class": 42}]}, TypeError, "ContextObject subclass"),
        (
            {"objects": [{"class": "logbook.Logger"}]},
            TypeError,
            "ContextObject subclass",
        ),
        (
            {"objects": [{"class": "logbook.info"}]},
            TypeError,
            "ContextObject subclass",
        ),
        (
            {"objects": [{"class": "no_such_logbook_module.Handler"}]},
            ModuleNotFoundError,
            "no_such_logbook_module",
        ),
        (
            {"objects": [{"class": "logbook.NoSuchHandler"}]},
            AttributeError,
            "NoSuchHandler",
        ),
    ],
)
def test_from_dict_invalid_config(config, error, message):
    with pytest.raises(error, match=message):
        logbook.NestedSetup.from_dict(config)


def test_from_dict_validates_before_opening_files(tmp_path):
    logfile = tmp_path / "must-not-exist.log"
    with pytest.raises(ValueError, match="missing 'class'"):
        logbook.NestedSetup.from_dict(
            {
                "objects": [
                    {"class": "logbook.FileHandler", "filename": logfile},
                    {},
                ]
            }
        )
    assert not logfile.exists()


def test_from_dict_closes_created_handlers_on_error(tmp_path):
    created = []
    closed = []

    class FileHandler(logbook.FileHandler):
        def __init__(self, filename):
            super().__init__(filename)
            created.append(self)

        def close(self):
            super().close()
            closed.append(self)
            raise OSError("cleanup failed")

    with pytest.raises(TypeError, match="unexpected"):
        logbook.NestedSetup.from_dict(
            {
                "objects": [
                    {"class": FileHandler, "filename": tmp_path / "first.log"},
                    {"class": "logbook.Processor"},
                    {"class": FileHandler, "filename": tmp_path / "second.log"},
                    {"class": "logbook.NullHandler", "unexpected": True},
                ]
            }
        )
    assert closed == created[::-1]
    assert all(handler.stream is None for handler in created)
    assert all(
        handler not in logbook.Handler.stack_manager.iter_context_objects()
        for handler in created
    )


def test_from_dict_cleanup_attribute_error_preserves_constructor_error(tmp_path):
    created = []

    class FileHandler(logbook.FileHandler):
        def __init__(self, filename):
            super().__init__(filename)
            created.append(self)

    class Processor(logbook.Processor):
        @property
        def close(self):
            raise RuntimeError("cannot look up close")

    with pytest.raises(LookupError, match="unknown level"):
        logbook.NestedSetup.from_dict(
            {
                "objects": [
                    {"class": FileHandler, "filename": tmp_path / "events.log"},
                    {"class": Processor},
                    {"class": "logbook.NullHandler", "level": "INVALID"},
                ]
            }
        )
    assert len(created) == 1
    assert created[0].stream is None


def test_from_dict_passes_nested_values_unchanged():
    class Processor(logbook.Processor):
        def __init__(self, options):
            super().__init__()
            self.options = options

    options = {"class": "an.application.setting", "items": [1, 2]}
    setup = logbook.NestedSetup.from_dict(
        {"objects": [{"class": Processor, "options": options}]}
    )
    assert setup.objects[0].options is options
