# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import inspect
from importlib.metadata import distribution
from pathlib import Path

from sphinx.util import inspect as sphinx_inspect

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "Logbook"
project_copyright = "2010, Armin Ronacher, Georg Brandl"
version = release = distribution("Logbook").version


# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.doctest",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "sphinxcontrib.towncrier.ext",
]

doctest_test_doctest_blocks = ""
doctest_default_flags = 0
doctest_global_setup = """
import logging as _logging

import logbook.base as _logbook_base

_record_factory = _logging.getLogRecordFactory()
_datetime_factory = _logbook_base._datetime_factory


def set_record_time(when):
    def record_factory(*args, **kwargs):
        record = _record_factory(*args, **kwargs)
        record.created = when.timestamp()
        return record

    record_time = _logbook_base._record_time_from_utc(when)
    _logging.setLogRecordFactory(record_factory)
    _logbook_base._datetime_factory = lambda: record_time


def reset_record_time():
    _logging.setLogRecordFactory(_record_factory)
    _logbook_base._datetime_factory = _datetime_factory
"""

# Render pending newsfragments at the top of the changelog, so that previews
# built from pull requests show their entries.
towncrier_draft_include_empty = False
towncrier_draft_working_directory = str(Path(__file__).resolve().parent.parent)

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]


# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "furo"
html_logo = "logbook-logo.png"


# -- Extension configuration -------------------------------------------------

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}


def _deprecated_class_signature(
    app, what, name, obj, options, signature, return_annotation
):
    # @deprecated wraps a class's __new__ in a (*args, **kwargs) function, and
    # autodoc reads the class signature from __new__ before __init__. A class
    # with its own __new__ is left to autodoc, which follows __wrapped__.
    if (
        what == "class"
        and hasattr(obj, "__deprecated__")
        and not inspect.isfunction(inspect.unwrap(obj.__new__))
        and obj.__init__ is not object.__init__
    ):
        init = sphinx_inspect.signature(obj.__init__, bound_method=True)
        signature = sphinx_inspect.stringify_signature(
            init, show_return_annotation=False, unqualified_typehints=True
        )
        return signature, return_annotation
    return None


def setup(app):
    app.connect("autodoc-process-signature", _deprecated_class_signature)
