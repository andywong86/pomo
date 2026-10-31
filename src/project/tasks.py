"""Development task entry points for `uv run -- <task>` commands."""

from __future__ import annotations

import pathlib
import shutil
import subprocess


def _run(*args: str) -> int:
    return subprocess.run(args, check=False).returncode


def _run_and_exit(*args: str) -> None:
    raise SystemExit(_run(*args))


def test() -> None:
    _run_and_exit("pytest", "--cov", "--cov-report=term-missing")


def typecheck() -> None:
    _run_and_exit("mypy", ".")


def lint() -> None:
    _run_and_exit("ruff", "check", "--fix")


def format() -> None:
    _run_and_exit("ruff", "format")


def clean() -> None:
    root = pathlib.Path.cwd()
    directories = [
        root / "dist",
        root / "build",
        root / ".mypy_cache",
        root / ".pytest_cache",
        root / ".ruff_cache",
        root / ".coverage",
        root / "htmlcov",
    ]
    directories.extend(root.glob("*.egg-info"))
    directories.extend(root.rglob("__pycache__"))

    for directory in directories:
        if directory.is_dir():
            shutil.rmtree(directory)

    for pattern in ("*.pyc", "*.pyo"):
        for file_path in root.rglob(pattern):
            if file_path.is_file():
                file_path.unlink()


def build() -> None:
    for command in [
        ("pytest", "--cov", "--cov-report=term-missing"),
        ("mypy", "."),
        ("ruff", "format"),
        ("ruff", "check", "--fix"),
        ("uv", "build"),
    ]:
        returncode = _run(*command)
        if returncode != 0:
            raise SystemExit(returncode)
