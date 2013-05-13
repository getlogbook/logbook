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
        "execnet",
        "Jinja2",
        "nose",
    ]

    if python_version < "2.6":
        deps.extend([
            "ssl",
            "multiprocessing",
            "pyzmq==2.1.11",
            "sqlalchemy",
            "simplejson",
        ])
    else:
        deps.append("sqlalchemy")
        deps.append("pyzmq")
    if python_version < "2.7":
        deps.append("unittest2")
    print("Setting up dependencies...")
    _execute("pip install %s" % " ".join(deps), shell=True)
