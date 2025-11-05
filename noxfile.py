# Thanks to pyca/cryptography for the way to get rust coverage out
# SPDX-License-Identifier: Apache-2.0 OR BSD-3-Clause
# SPDX-FileCopyrightText: pyca/cryptography contributors
# SPDX-FileCopyrightText: Frazer McLean
import glob
import json
import re
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from itertools import chain
from pathlib import Path
from uuid import uuid4

import nox

nox.options.reuse_existing_virtualenvs = True
nox.options.default_venv_backend = "uv"

PYTHON_VERSIONS = ["3.9", "3.10", "3.11", "3.12", "3.13", "3.14", "3.14t"]

SUPPORTED_EXTRAS = [
    "brotli",
    "execnet",
    "jinja",
    "nteventlog",
    "redis",
    "sqlalchemy",
    "zmq",
]
SUPPORTED_EXTRAS_FREETHREADING = [
    "execnet",
    "jinja",
    "redis",
    "zmq",
]


@nox.session(python="3.13")
def docs(session: nox.Session) -> None:
    session.run_install(
        "uv",
        "sync",
        "--no-dev",
        "--group=docs",
        f"--python={session.virtualenv.location}",
        env={"UV_PROJECT_ENVIRONMENT": session.virtualenv.location},
    )

    temp_dir = session.create_tmp()
    session.run(
        "sphinx-build",
        "-W",
        "-b",
        "html",
        "-d",
        f"{temp_dir}/doctrees",
        "docs",
        "docs/_build/html",
    )
    session.run(
        "sphinx-build",
        "-W",
        "-b",
        "linkcheck",
        "-d",
        f"{temp_dir}/doctrees",
        "docs",
        "docs/_build/html",
    )


@nox.session(python=PYTHON_VERSIONS)
@nox.parametrize("speedups", [False, True], ids=["nospeedups", "speedups"])
def tests(session: nox.Session, speedups: bool) -> None:
    prof_location = Path(".rust-cov", str(uuid4())).absolute()
    rustflags = session.env.get("RUSTFLAGS", "")
    rustflags = f"-Cinstrument-coverage {rustflags}"
    session.env.update(
        {
            "RUSTFLAGS": rustflags,
            "LLVM_PROFILE_FILE": str(prof_location / "cov-%p.profraw"),
        }
    )
    is_freethreaded = session.python.endswith("t")
    supported_extras = (
        SUPPORTED_EXTRAS_FREETHREADING if is_freethreaded else SUPPORTED_EXTRAS
    )
    session.run_install(
        "uv",
        "sync",
        *(f"--extra={extra}" for extra in supported_extras),
        "--no-editable",
        "--no-dev",
        "--group=coverage",
        "--group=test",
        f"--python={session.virtualenv.location}",
        *([] if is_freethreaded else ["--group=gevent"]),
        env={
            "UV_PROJECT_ENVIRONMENT": session.virtualenv.location,
            "DISABLE_LOGBOOK_CEXT": "" if speedups else "1",
            "SETUPTOOLS_RUST_CARGO_PROFILE": "release",
        },
    )

    session.run("coverage", "run", "-m", "pytest", *session.posargs)
    if speedups:
        libs = glob.glob(
            f"{session.virtualenv.location}/lib/**/logbook/_speedups.*",
            recursive=True,
        )
        [rust_so] = libs
        process_rust_coverage(session, [rust_so], prof_location)


@nox.session(name="test-min-deps", python=PYTHON_VERSIONS)
def test_min_deps(session: nox.Session) -> None:
    is_freethreaded = session.python.endswith("t")
    supported_extras = (
        SUPPORTED_EXTRAS_FREETHREADING if is_freethreaded else SUPPORTED_EXTRAS
    )
    with restore_file("uv.lock"):
        session.run_install(
            "uv",
            "sync",
            *(f"--extra={extra}" for extra in supported_extras),
            "--no-editable",
            "--no-dev",
            "--group=coverage",
            "--group=test",
            *([] if is_freethreaded else ["--group=gevent"]),
            "--resolution=lowest-direct",
            f"--python={session.virtualenv.location}",
            env={
                "UV_PROJECT_ENVIRONMENT": session.virtualenv.location,
                "SETUPTOOLS_RUST_CARGO_PROFILE": "release",
            },
        )

        session.run("pytest", *session.posargs)


@nox.session(name="test-latest", python=PYTHON_VERSIONS)
def test_latest(session: nox.Session) -> None:
    is_freethreaded = session.python.endswith("t")
    session.run_install(
        "uv",
        "sync",
        "--no-install-project",
        "--no-dev",
        "--group=coverage",
        "--group=test",
        *([] if is_freethreaded else ["--group=gevent"]),
        f"--python={session.virtualenv.location}",
        env={"UV_PROJECT_ENVIRONMENT": session.virtualenv.location},
    )
    supported_extras = (
        SUPPORTED_EXTRAS_FREETHREADING if is_freethreaded else SUPPORTED_EXTRAS
    )
    session.run_install(
        "uv",
        "pip",
        "install",
        "--upgrade",
        f".[{','.join(supported_extras)}]",
        *([] if is_freethreaded else ["gevent"]),
        f"--python={session.virtualenv.location}",
        env={
            "UV_PROJECT_ENVIRONMENT": session.virtualenv.location,
            "SETUPTOOLS_RUST_CARGO_PROFILE": "release",
        },
    )

    session.run("pytest", *session.posargs)


@nox.session(python=PYTHON_VERSIONS)
def rust(session: nox.Session) -> None:
    prof_location = Path(".rust-cov", str(uuid4())).absolute()
    rustflags = session.env.get("RUSTFLAGS", "")
    rustflags = f"-Cinstrument-coverage {rustflags}"
    session.env.update(
        {
            "RUSTFLAGS": rustflags,
            "LLVM_PROFILE_FILE": str(prof_location / "cov-%p.profraw"),
        }
    )

    build_output = session.run(
        "cargo",
        "test",
        "--no-default-features",
        "--all",
        "--no-run",
        "--quiet",
        "--message-format=json",
        external=True,
        silent=True,
    )
    session.run("cargo", "test", "--no-default-features", "--all", external=True)

    if build_output is not None:
        assert isinstance(build_output, str)
        rust_tests = []
        for line in build_output.splitlines():
            data = json.loads(line)
            if data.get("profile", {}).get("test", False):
                rust_tests.extend(data["filenames"])

        process_rust_coverage(session, rust_tests, prof_location)


@contextmanager
def restore_file(path: str) -> Iterator[None]:
    with open(path, "rb") as f:
        original = f.read()
    try:
        yield
    finally:
        with open(path, "wb") as f:
            f.write(original)


LCOV_SOURCEFILE_RE = re.compile(
    r"^SF:.*[\\/]src[\\/]rust[\\/](.*)$", flags=re.MULTILINE
)
BIN_EXT = ".exe" if sys.platform == "win32" else ""


def process_rust_coverage(
    session: nox.Session,
    rust_binaries: list[str],
    prof_raw_location: Path,
) -> None:
    # Hitting weird issues merging Windows and Linux Rust coverage, so just
    # say the hell with it.
    if sys.platform == "win32":
        return

    target_libdir = session.run(
        "rustc", "--print", "target-libdir", external=True, silent=True
    )
    if target_libdir is not None:
        target_bindir = Path(target_libdir).parent / "bin"

        profraws = [
            str(prof_raw_location / p) for p in prof_raw_location.glob("*.profraw")
        ]
        session.run(
            str(target_bindir / ("llvm-profdata" + BIN_EXT)),
            "merge",
            "-sparse",
            *profraws,
            "-o",
            "rust-cov.profdata",
            external=True,
        )

        lcov_data = session.run(
            str(target_bindir / ("llvm-cov" + BIN_EXT)),
            "export",
            rust_binaries[0],
            *chain.from_iterable(["-object", b] for b in rust_binaries[1:]),
            "-instr-profile=rust-cov.profdata",
            "--ignore-filename-regex=[/\\].cargo[/\\]",
            "--ignore-filename-regex=[/\\]rustc[/\\]",
            "--ignore-filename-regex=[/\\].rustup[/\\]toolchains[/\\]",
            "--ignore-filename-regex=[/\\]target[/\\]",
            "--format=lcov",
            silent=True,
            external=True,
        )
        assert isinstance(lcov_data, str)
        lcov_data = LCOV_SOURCEFILE_RE.sub(
            lambda m: "SF:src/rust/" + m.group(1).replace("\\", "/"),
            lcov_data.replace("\r\n", "\n"),
        )
        with open(f"{uuid4()}.lcov", "w") as f:
            f.write(lcov_data)
