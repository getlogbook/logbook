#! /usr/bin/python

if __name__ == '__main__':
    import platform
    if platform.python_version() >= "2.7":
        import unittest
    else:
        import unittest2 as unittest
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    unittest.main("logbook.testsuite", "suite")
