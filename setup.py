import os
import platform

from setuptools import Extension, setup

IS_CPYTHON = platform.python_implementation() == "CPython"
DISABLE_EXTENSION = bool(os.environ.get("DISABLE_LOGBOOK_CEXT"))


def status_msgs(*msgs):
    print("*" * 75)
    for msg in msgs:
        print(msg)
    print("*" * 75)


if not IS_CPYTHON:
    status_msgs(
        "WARNING: C extensions are not supported on this Python platform, "
        "speedups are not enabled.",
    )
    ext_modules = []
elif DISABLE_EXTENSION:
    status_msgs(
        "DISABLE_LOGBOOK_CEXT is set; not attempting to build C extensions.",
    )
    ext_modules = []
else:
    from Cython.Build import cythonize

    ext_modules = cythonize(
        [Extension("logbook._speedups", sources=["src/cython/speedups.pyx"])],
        language_level=3,
    )

setup(ext_modules=ext_modules)
