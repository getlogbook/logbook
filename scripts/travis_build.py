#! /usr/bin/python
from __future__ import print_function
import ast
import os
import subprocess
import sys

_PYPY = hasattr(sys, "pypy_version_info")

if __name__ == '__main__':
    use_cython = ast.literal_eval(os.environ["USE_CYTHON"])
    if use_cython and _PYPY:
        print("PyPy+Cython configuration skipped")
    else:
        sys.exit(
            subprocess.call(
                "make cybuild test" if use_cython else "make test", shell=True)
        )
