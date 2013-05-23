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
        "nose",
        "sqlalchemy",
    ]

    if python_version < "2.6":
        deps.extend([
            "ssl",
            "multiprocessing",
            "pyzmq==2.1.11",
            "simplejson",
        ])
    else:
        deps.extend([
            "pyzmq",
        ])

    # Jinja2 is a bit fragmented...
    if python_version < "3.3":
        deps.append("Jinja2==2.6")
    else:
        deps.append("Jinja2")


    if python_version < "2.7":
        deps.append("unittest2")
    print("Setting up dependencies...")
    _execute("pip install %s" % " ".join(deps), shell=True)
