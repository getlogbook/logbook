#! /usr/bin/python
import os
import sys


if __name__ == '__main__':
    mirror = sys.argv[1]
    f = open(os.path.expanduser("~/.pydistutils.cfg"), "w")
    f.write("""
[easy_install]
index_url = %s
""" % mirror)
    f.close()
    pip_dir = os.path.expanduser("~/.pip")
    if not os.path.isdir(pip_dir):
        os.makedirs(pip_dir)
    f = open(os.path.join(pip_dir, "pip.conf"), "w")
    f.write("""
[global]
index-url = %s

[install]
use-mirrors = true
""" % mirror)
    f.close()
