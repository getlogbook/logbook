#!/usr/bin/env python
"""
Runs the benchmarks
"""

import importlib.metadata
import importlib.util
import os
import re
import sys
from subprocess import Popen

try:
    version = importlib.metadata.version("logbook")
except ModuleNotFoundError:
    version = "unknown version"


_filename_re = re.compile(r"^bench_(.*?)\.py$")
bench_directory = os.path.abspath(os.path.dirname(__file__))


def list_benchmarks():
    result = []
    for name in os.listdir(bench_directory):
        match = _filename_re.match(name)
        if match is not None:
            result.append(match.group(1))
    result.sort(key=lambda x: (x.startswith("logging_"), x.lower()))
    return result


def run_bench(name, use_gevent=False):
    sys.stdout.write("%-32s" % name)  # noqa: UP031
    sys.stdout.flush()
    Popen(
        [
            sys.executable,
            "-mtimeit",
            "-s",
            "from bench_%s import run" % name,  # noqa: UP031
            "from logbook.concurrency import enable_gevent",
            "enable_gevent()" if use_gevent else "",
            "run()",
        ]
    ).wait()


def bench_wrapper(use_gevent=False):
    print("=" * 80)
    print(f"Running benchmark with Logbook {version} (gevent enabled={use_gevent})")
    print("-" * 80)
    os.chdir(bench_directory)
    for bench in list_benchmarks():
        run_bench(bench, use_gevent)
    print("-" * 80)


def main():
    bench_wrapper(False)
    if importlib.util.find_spec("gevent") is not None:
        bench_wrapper(True)


if __name__ == "__main__":
    main()
