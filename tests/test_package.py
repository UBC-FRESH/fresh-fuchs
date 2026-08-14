from __future__ import annotations

import importlib

import typer.testing
from typer.testing import CliRunner

from fresh_fuchs import __version__
from fresh_fuchs.cli import app

runner = CliRunner()


def test_version() -> None:
    # Single source of truth: the installed package metadata (pyproject.toml).
    from importlib import metadata as importlib_metadata

    assert __version__ == importlib_metadata.version("fresh-fuchs")
    assert __version__ == "0.1.0a1"


def test_cli_importable() -> None:
    assert app.info.name == "fresh-fuchs"


def test_cli_version_command() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_cli_lists_stub_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("build-model", "scenario-run", "inner-run", "outer-run", "pipeline-run"):
        assert command in result.stdout


def test_module_stubs_importable() -> None:
    for module in (
        "instance",
        "economy",
        "scenario",
        "inner",
        "outer",
        "orchestration",
    ):
        imported = importlib.import_module(f"fresh_fuchs.{module}")
        assert imported.__doc__


def test_typer_testing_available() -> None:
    assert typer.testing
