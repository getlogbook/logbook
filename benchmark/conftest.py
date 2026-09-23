"""Shared fixtures for the CodSpeed benchmarks.

The benchmarks in this directory are run with ``pytest --codspeed`` (see the
``benchmarks`` GitHub Actions workflow).  They live outside of ``tests/`` so
that a regular ``pytest`` run does not collect them.
"""

import pytest

from logbook import Logger


@pytest.fixture
def logger():
    return Logger("Test logger")
