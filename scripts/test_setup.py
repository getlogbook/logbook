#! /usr/bin/python
import pip
import sys

if __name__ == '__main__':
    python_version = sys.version_info

    deps = [
        "execnet>=1.0.9",
        "pytest",
        "pyzmq",
        "sqlalchemy",
    ]

    if (3, 2) <= python_version < (3, 3):
        deps.append("markupsafe==0.15")
        deps.append("Jinja2==2.6")
    else:
        deps.append("Jinja2")
    print("Setting up dependencies...")
    result = pip.main(["install"] + deps)
    sys.exit(result)
