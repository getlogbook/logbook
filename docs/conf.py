# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

from importlib.metadata import distribution
from pathlib import Path

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
