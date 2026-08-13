"""Thin Typer CLI over the fresh-fuchs Python APIs.

Stub commands for Phase 0; each phase wires its API behind a command.
"""

from __future__ import annotations

import typer

from fresh_fuchs import __version__

app = typer.Typer(
    name="fresh-fuchs",
    help="Stochastic, risk-aware forest landscape planning (TSA29 mini).",
    no_args_is_help=True,
)


@app.command("version")
def version() -> None:
    """Print the package version."""
    typer.echo(__version__)


@app.command("build-model")
def build_model() -> None:
    """Build the extended ws3 model from the tsa29mini bundle (Phase 1)."""
    typer.echo("not implemented (Phase 1)")


@app.command("scenario-run")
def scenario_run() -> None:
    """Generate full-MC scenarios (Phase 3)."""
    typer.echo("not implemented (Phase 3)")


@app.command("inner-run")
def inner_run() -> None:
    """Solve the inner Model I LP for a scenario (Phase 2-3)."""
    typer.echo("not implemented (Phase 2-3)")


@app.command("outer-run")
def outer_run() -> None:
    """Evaluate policies on NPV distributions (Phase 4)."""
    typer.echo("not implemented (Phase 4)")


@app.command("pipeline-run")
def pipeline_run() -> None:
    """Run the end-to-end pipeline (Phase 5)."""
    typer.echo("not implemented (Phase 5)")


if __name__ == "__main__":
    app()
