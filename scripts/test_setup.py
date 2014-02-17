#! /usr/bin/python
import platform
import subprocess
import sys

def _execute(*args, **kwargs):
    result = subprocess.call(*args, **kwargs)
    if result != 0:
        sys.exit(result)

if __name__ == '__main__':
    python_version = platform.python_version()

    deps = [
        "execnet>=1.0.9",
        "nose",
        "pyzmq",
        "sqlalchemy",
    ]

    if python_version < "2.7":
        deps.append("unittest2")
    if python_version.startswith('3.2.'):
        deps.append("markupsafe==0.15")
        deps.append("Jinja2==2.6")
    else:
        deps.append("Jinja2")
    print("Setting up dependencies...")
    _execute(["pip",  "install"] + deps, shell=False)
