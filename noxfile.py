from collections.abc import Iterator
from contextlib import contextmanager

import nox

nox.options.reuse_existing_virtualenvs = True
nox.options.default_venv_backend = "uv"


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


@nox.session(python=["3.9", "3.10", "3.11", "3.12", "3.13", "3.14"])
@nox.parametrize("speedups", [False, True], ids=["nospeedups", "speedups"])
def tests(session: nox.Session, speedups: bool) -> None:
    session.run_install(
        "uv",
        "sync",
        "--all-extras",
        "--no-editable",
        f"--python={session.virtualenv.location}",
        env={
            "UV_PROJECT_ENVIRONMENT": session.virtualenv.location,
            "DISABLE_LOGBOOK_CEXT": "" if speedups else "1",
        },
    )

    session.run("pytest", *session.posargs)


@nox.session(
    name="test-min-deps", python=["3.9", "3.10", "3.11", "3.12", "3.13", "3.14"]
)
def test_min_deps(session: nox.Session) -> None:
    with restore_file("uv.lock"):
        session.run_install(
            "uv",
            "sync",
            "--all-extras",
            "--no-editable",
            "--resolution=lowest-direct",
            f"--python={session.virtualenv.location}",
            env={"UV_PROJECT_ENVIRONMENT": session.virtualenv.location},
        )

        session.run("pytest", *session.posargs)


@nox.session(name="test-latest", python=["3.9", "3.10", "3.11", "3.12", "3.13", "3.14"])
def test_latest(session: nox.Session) -> None:
    session.run_install(
        "uv",
        "sync",
        "--no-install-project",
        f"--python={session.virtualenv.location}",
        env={"UV_PROJECT_ENVIRONMENT": session.virtualenv.location},
    )
    session.run_install(
        "uv",
        "pip",
        "install",
        "--upgrade",
        ".[all]",
        f"--python={session.virtualenv.location}",
        env={"UV_PROJECT_ENVIRONMENT": session.virtualenv.location},
    )

    session.run("pytest", *session.posargs)


@nox.session(python=["3.9", "3.10", "3.11", "3.12", "3.13", "3.14"])
def rust(session: nox.Session) -> None:
    session.run(
        "cargo",
        "test",
        "--no-default-features",
        "--all",
        external=True,
    )


@contextmanager
def restore_file(path: str) -> Iterator[None]:
    with open(path, "rb") as f:
        original = f.read()
    try:
        yield
    finally:
        with open(path, "wb") as f:
            f.write(original)
