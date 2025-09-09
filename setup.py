import os
import platform

from setuptools import setup

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
    kwargs = {}
elif DISABLE_EXTENSION:
    status_msgs(
        "DISABLE_LOGBOOK_CEXT is set; not attempting to build C extensions.",
    )
    kwargs = {}
else:
    from setuptools_rust import RustExtension

    kwargs = {
        "rust_extensions": [
            RustExtension(
                "logbook._speedups",
                "src/rust/Cargo.toml",
                rust_version=">=1.74",
            )
        ]
    }

setup(**kwargs)
