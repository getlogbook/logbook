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
    ]

    if python_version < "2.6":
        deps.append("ssl")
        deps.append("multiprocessing")
        if python_version < "2.5":
            # 2.4
            deps.extend([
                "pysqlite",
                "simplejson==2.0.9",
                "sqlalchemy==0.7.0",
            ])
        else:
            # 2.5
            deps.extend([
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
