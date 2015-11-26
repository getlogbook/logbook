# -*- coding: utf-8 -*-
import os

import pytest

from .utils import appveyor, travis

@appveyor
def test_appveyor_speedups():
    if os.environ.get('CYBUILD'):
        import logbook._speedups
    else:
        with pytest.raises(ImportError):
            import logbook._speedups

@travis
def test_travis_speedups():
    if os.environ.get('CYBUILD'):
        import logbook._speedups
    else:
        with pytest.raises(ImportError):
            import logbook._speedups
