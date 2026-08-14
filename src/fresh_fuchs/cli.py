"""Thin Typer CLI over the fresh-fuchs Python APIs.

Phase 0 stubs; Phase 1 wires ``build-model`` and ``baseline-run``.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import typer

from fresh_fuchs import __version__
from fresh_fuchs.economy import (
    NpvConfig,
    PriceGroup,
    add_npv_problem,
    interior_surface,
    sawlog_basis_salvage_margin,
    solve_npv,
    species_by_dtk_from_areas,
)
from fresh_fuchs.instance import (
    BaselineConfig,
    InstanceConfig,
    add_even_flow_problem,
    apply_retention_split,
    bootstrap_model,
    build_model,
    development_type_species,
    load_fragments,
    load_species_by_au,
    managed_landscape_composition,
    prepare_optimization,
    run_oldest_first_heuristic,
    solve_even_flow,
    summarize,
)

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
def build_model_cmd(
    bundle_dir: Path = typer.Option(..., "--bundle-dir", help="Bundle directory (bundle tables)."),
    fragments_path: Path = typer.Option(..., "--fragments", help="Fragments shapefile path."),
    model_path: Path = typer.Option(
        Path("outputs") / "tsa29mini" / "ws3_woodstock_bootstrap_model",
        "--model-path",
        help="Directory for the Woodstock-format sections.",
    ),
    horizon: int = typer.Option(30, "--horizon", min=1),
) -> None:
    """Build the ws3 model from the tsa29mini bundle (Phase 1)."""
    config = InstanceConfig(
        bundle_dir=bundle_dir,
        fragments_path=fragments_path,
        model_path=model_path,
        horizon=horizon,
    )
    model, summary = build_model(config)
    typer.echo(f"Built model {config.model_name}: {len(model.dtypes):,} development types")
    typer.echo(
        f"Total area: {summary['total_area_ha']:.1f} ha | "
        f"managed: {summary['managed_area_ha']:.1f} ha | "
        f"AUs: {summary['analysis_units']} | curves: {summary['curves']}"
    )
    for path in summary["files"]:
        typer.echo(f"  wrote {path}")


@app.command("baseline-run")
def baseline_run_cmd(
    model_path: Path = typer.Option(
        Path("outputs") / "tsa29mini" / "ws3_woodstock_bootstrap_model",
        "--model-path",
        help="Directory with the Woodstock-format sections.",
    ),
    model_name: str = typer.Option("tsa29mini", "--model-name"),
    max_initial_age: int = typer.Option(436, "--max-initial-age"),
    horizon: int = typer.Option(30, "--horizon", min=1),
    out_csv: Path | None = typer.Option(None, "--out", help="Write per-period results CSV."),
) -> None:
    """Run the even-flow LP and oldest-first heuristic baselines (Phase 1)."""
    config = InstanceConfig(model_name=model_name, model_path=model_path, horizon=horizon)
    model = prepare_optimization(
        bootstrap_model(config), max_initial_age=max_initial_age, config=config
    )

    problem = add_even_flow_problem(model, BaselineConfig(workers=1))
    lp = solve_even_flow(model, problem)
    lp_summary = summarize(lp, period_length=config.period_length)

    typer.echo("Even-flow LP (managed land base):")
    typer.echo(f"  status: {problem.status()}")
    typer.echo(f"  mean annual harvest: {lp_summary['mean_annual_harvest_m3_per_yr']:.0f} m3/yr")

    heuristic = run_oldest_first_heuristic(model)
    heuristic_summary = summarize(heuristic, period_length=config.period_length)
    typer.echo("Oldest-first heuristic:")
    typer.echo(
        f"  mean annual harvest: {heuristic_summary['mean_annual_harvest_m3_per_yr']:.0f} m3/yr"
    )

    if out_csv is not None:
        lp["solver"] = "evenflow-lp"
        heuristic["solver"] = "oldest-first"
        heuristic["growing_stock_m3"] = float("nan")
        columns = ["solver", "period", "harvest_area_ha", "harvest_volume_m3", "growing_stock_m3"]
        stacked = pd.concat([lp[columns], heuristic[columns]], ignore_index=True)
        out_csv.parent.mkdir(parents=True, exist_ok=True)
        stacked.to_csv(out_csv, index=False)
        typer.echo(f"  wrote {out_csv}")


@app.command("species-composition")
def species_composition_cmd(
    bundle_dir: Path = typer.Option(..., "--bundle-dir", help="Bundle directory (bundle tables)."),
    fragments_path: Path = typer.Option(..., "--fragments", help="Fragments shapefile path."),
    ageclass_width: int = typer.Option(10, "--ageclass-width", min=1),
) -> None:
    """Report managed-land-base species composition by static class (Phase 1)."""
    species_by_au = load_species_by_au(bundle_dir)
    fragments = load_fragments(fragments_path)
    areas = apply_retention_split(
        fragments,
        ageclass_width=ageclass_width,
        species_by_au=species_by_au,
    )
    composition = managed_landscape_composition(areas)
    dts = development_type_species(areas)

    typer.echo("Managed land-base composition by primary species class:")
    for _, row in composition.iterrows():
        typer.echo(f"  {row['species']:>4}  {row['area_ha']:,.1f} ha  {row['share']:6.1%}")
    typer.echo(f"Species-aware development-type classes: {len(dts)}")


@app.command("economy-run")
def economy_run_cmd(
    bundle_dir: Path = typer.Option(..., "--bundle-dir", help="Bundle directory (bundle tables)."),
    fragments_path: Path = typer.Option(..., "--fragments", help="Fragments shapefile path."),
    model_path: Path = typer.Option(
        Path("outputs") / "tsa29mini" / "ws3_woodstock_bootstrap_model",
        "--model-path",
        help="Directory with the Woodstock-format sections.",
    ),
    model_name: str = typer.Option("tsa29mini", "--model-name"),
    max_initial_age: int = typer.Option(436, "--max-initial-age"),
    horizon: int = typer.Option(30, "--horizon", min=1),
    out_csv: Path | None = typer.Option(None, "--out", help="Write per-period results CSV."),
) -> None:
    """Run the NPV-max even-flow LP on the built model (Phase 2)."""
    config = InstanceConfig(model_name=model_name, model_path=model_path, horizon=horizon)
    model = prepare_optimization(
        bootstrap_model(config), max_initial_age=max_initial_age, config=config
    )

    species_by_au = load_species_by_au(bundle_dir)
    fragments = load_fragments(fragments_path)
    areas = apply_retention_split(fragments, species_by_au=species_by_au)
    species_by_dtk = species_by_dtk_from_areas(areas)
    surface = interior_surface()

    problem = add_npv_problem(
        model,
        NpvConfig(workers=1),
        surface=surface,
        species_by_dtk=species_by_dtk,
    )
    results = solve_npv(model, problem)
    summary = summarize(results, period_length=config.period_length)

    typer.echo(f"NPV-max even-flow LP ({surface.discount.annual_rate:.0%} discount):")
    typer.echo(f"  status: {problem.status()}")
    typer.echo(f"  mean annual harvest: {summary['mean_annual_harvest_m3_per_yr']:.0f} m3/yr")
    typer.echo(f"  total harvested area: {summary['total_harvested_area_ha']:.0f} ha")
    typer.echo("Salvage margin anchors (zero subsidy, sawlog basis, CAD/m3):")
    typer.echo(f"  SPF: {sawlog_basis_salvage_margin(surface, PriceGroup.SPF):.2f}")
    typer.echo(f"  Df-Larch: {sawlog_basis_salvage_margin(surface, PriceGroup.DFLARCH):.2f}")

    if out_csv is not None:
        results["solver"] = "npv-lp"
        columns = ["solver", "period", "harvest_area_ha", "harvest_volume_m3", "growing_stock_m3"]
        out_csv.parent.mkdir(parents=True, exist_ok=True)
        results[columns].to_csv(out_csv, index=False)
        typer.echo(f"  wrote {out_csv}")


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
