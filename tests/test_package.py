from __future__ import annotations

from fresh_fuchs import __version__


def test_version() -> None:
    assert __version__ == "0.1.0a0"


def test_cli_importable() -> None:
    from fresh_fuchs.cli import app

    assert app.info.name == "fresh-fuchs"
