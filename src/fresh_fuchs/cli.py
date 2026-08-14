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
from fresh_fuchs.scenario.fire import DEFAULT_SEVERITY

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
def scenario_run_cmd(
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
    n_scenarios: int = typer.Option(10, "--n-scenarios", min=1),
    master_seed: int = typer.Option(42, "--master-seed"),
    workers: int = typer.Option(1, "--workers", min=1),
    out_dir: Path = typer.Option(
        Path("outputs") / "tsa29mini" / "scenario_run",
        "--out-dir",
        help="Directory for the run record (JSON + schedule CSVs + summary).",
    ),
) -> None:
    """Run the scenario -> inner-LP pipeline (Phase 3, P3.5).

    Generates a seed-fixed fire scenario catalogue from the bundle zones'
    MFRI annual burn rates, solves the fire-aware even-flow/NPV LP once per
    scenario (full foresight), and writes run records with provenance.
    """
    import pandas as pd

    from fresh_fuchs.economy.types import Provenance
    from fresh_fuchs.scenario.distributions import (
        DistributionFamily,
        ParameterDistribution,
        UncertaintyDimension,
        UncertaintyVector,
    )
    from fresh_fuchs.scenario.fire import MFRI_YEARS_BY_ZONE
    from fresh_fuchs.scenario.pipeline import run_scenario_pipeline, write_pipeline_record
    from fresh_fuchs.scenario.records import ScenarioGenerationParams, generate_scenarios

    config = InstanceConfig(model_name=model_name, model_path=model_path, horizon=horizon)

    au_table = pd.read_csv(bundle_dir / "au_table.csv")
    au_table["zone"] = au_table["stratum_code"].str.split("_").str[0].str.upper()
    zone_by_au = {int(r.au_id): r.zone for r in au_table.itertuples()}
    zones = sorted({z for z in zone_by_au.values() if z in MFRI_YEARS_BY_ZONE})
    missing = sorted({z for z in zone_by_au.values() if z not in MFRI_YEARS_BY_ZONE})
    if missing:
        typer.echo(f"warning: zones without MFRI mapping ignored: {missing}")
    zone_burn_rates = {zone: 1.0 / MFRI_YEARS_BY_ZONE[zone] for zone in zones}
    typer.echo(f"zones {zones} annual burn rates {zone_burn_rates}")

    species_by_au = load_species_by_au(bundle_dir)
    fragments = load_fragments(fragments_path)
    areas = apply_retention_split(fragments, species_by_au=species_by_au)
    species_by_dtk = species_by_dtk_from_areas(areas)

    provenance = Provenance(
        source="tsa29mini bundle scenario catalogue (MFRI by zone)",
        as_of="2026-08-14",
        units="multiplier",
        basis="Gaussian burn-rate multiplier (mean 1.0, std 0.2); fixed price 1.0",
    )
    vector = UncertaintyVector(
        distributions={
            UncertaintyDimension.FIRE_BURN_RATE: ParameterDistribution(
                name="burn_rate_multiplier",
                family=DistributionFamily.GAUSSIAN,
                provenance=provenance,
                mean=1.0,
                std=0.2,
            ),
            UncertaintyDimension.PRICE: ParameterDistribution(
                name="price_factor",
                family=DistributionFamily.FIXED,
                provenance=provenance,
                value=1.0,
            ),
        }
    )
    params = ScenarioGenerationParams(
        n_scenarios=n_scenarios,
        master_seed=master_seed,
        horizon=horizon,
        period_length=config.period_length,
        zone_burn_rates=zone_burn_rates,
        vector=vector,
        severity=DEFAULT_SEVERITY,
        provenance=provenance,
    )
    scenarios = generate_scenarios(params)

    record = run_scenario_pipeline(
        scenarios=scenarios,
        config=config,
        surface=interior_surface(),
        species_by_dtk=species_by_dtk,
        zone_by_au=zone_by_au,
        max_initial_age=max_initial_age,
        n_workers=workers,
    )
    written = write_pipeline_record(record, out_dir)

    typer.echo(
        f"scenario-run complete ({record.n_scenarios} scenarios, {record.n_workers} workers):"
    )
    typer.echo(f"  statuses: {sorted({s.status for s in record.scenarios})}")
    npvs = [s.npv for s in record.scenarios]
    typer.echo(f"  NPV: mean {sum(npvs) / len(npvs):.0f}  min {min(npvs):.0f}  max {max(npvs):.0f}")
    mean_annual = sum(s.mean_annual_harvest_m3_per_yr for s in record.scenarios) / len(
        record.scenarios
    )
    typer.echo(f"  mean annual harvest: {mean_annual:.0f} m3/yr")
    for path in written:
        typer.echo(f"  wrote {path}")


@app.command("policy-grid")
def policy_grid_cmd(
    bundle_dir: Path = typer.Option(..., "--bundle-dir", help="Bundle directory (bundle tables)."),
    fragments_path: Path = typer.Option(..., "--fragments", help="Fragments shapefile path."),
    model_path: Path = typer.Option(
        Path("outputs") / "tsa29mini" / "ws3_woodstock_bootstrap_model",
        "--model-path",
        help="Directory with the Woodstock-format sections.",
    ),
    model_name: str = typer.Option("tsa29mini", "--model-name"),
    grid_json: Path = typer.Option(
        ..., "--grid-json", help="PolicyGrid definition (JSON). See examples/."
    ),
    max_initial_age: int = typer.Option(436, "--max-initial-age"),
    horizon: int = typer.Option(30, "--horizon", min=1),
    n_scenarios: int = typer.Option(10, "--n-scenarios", min=1),
    master_seed: int = typer.Option(42, "--master-seed"),
    scenario_workers: int = typer.Option(1, "--scenario-workers", min=1),
    policy_workers: int = typer.Option(1, "--policy-workers", min=1),
    out_dir: Path = typer.Option(
        Path("outputs") / "tsa29mini" / "policy_grid",
        "--out-dir",
        help="Directory for grid records (per-policy runs + summaries).",
    ),
) -> None:
    """Run the outer policy grid search (Phase 4, P4.2).

    Expands the ``--grid-json`` PolicyGrid into its Cartesian product,
    evaluates every policy over the seed-fixed MC scenario catalogue
    (scenario -> inner-LP pipeline with the policy rows), and writes
    per-policy run records plus grid summaries.
    """
    import json

    from fresh_fuchs.economy.types import Provenance
    from fresh_fuchs.outer import PolicyGrid, run_grid, write_grid_record
    from fresh_fuchs.scenario.distributions import (
        DistributionFamily,
        ParameterDistribution,
        UncertaintyDimension,
        UncertaintyVector,
    )
    from fresh_fuchs.scenario.fire import MFRI_YEARS_BY_ZONE
    from fresh_fuchs.scenario.records import ScenarioGenerationParams, generate_scenarios

    config = InstanceConfig(model_name=model_name, model_path=model_path, horizon=horizon)
    grid = PolicyGrid.model_validate(json.loads(grid_json.read_text()))

    au_table = pd.read_csv(bundle_dir / "au_table.csv")
    au_table["zone"] = au_table["stratum_code"].str.split("_").str[0].str.upper()
    zone_by_au = {int(r.au_id): r.zone for r in au_table.itertuples()}
    zones = sorted({z for z in zone_by_au.values() if z in MFRI_YEARS_BY_ZONE})
    missing = sorted({z for z in zone_by_au.values() if z not in MFRI_YEARS_BY_ZONE})
    if missing:
        typer.echo(f"warning: zones without MFRI mapping ignored: {missing}")
    zone_burn_rates = {zone: 1.0 / MFRI_YEARS_BY_ZONE[zone] for zone in zones}

    species_by_au = load_species_by_au(bundle_dir)
    fragments = load_fragments(fragments_path)
    areas = apply_retention_split(fragments, species_by_au=species_by_au)
    species_by_dtk = species_by_dtk_from_areas(areas)

    provenance = Provenance(
        source="tsa29mini bundle scenario catalogue (MFRI by zone)",
        as_of="2026-08-14",
        units="multiplier",
        basis="Gaussian burn-rate multiplier (mean 1.0, std 0.2); fixed price 1.0",
    )
    vector = UncertaintyVector(
        distributions={
            UncertaintyDimension.FIRE_BURN_RATE: ParameterDistribution(
                name="burn_rate_multiplier",
                family=DistributionFamily.GAUSSIAN,
                provenance=provenance,
                mean=1.0,
                std=0.2,
            ),
            UncertaintyDimension.PRICE: ParameterDistribution(
                name="price_factor",
                family=DistributionFamily.FIXED,
                provenance=provenance,
                value=1.0,
            ),
        }
    )
    params = ScenarioGenerationParams(
        n_scenarios=n_scenarios,
        master_seed=master_seed,
        horizon=horizon,
        period_length=config.period_length,
        zone_burn_rates=zone_burn_rates,
        vector=vector,
        severity=DEFAULT_SEVERITY,
        provenance=provenance,
    )
    scenarios = generate_scenarios(params)

    record = run_grid(
        grid=grid,
        scenarios=scenarios,
        config=config,
        surface=interior_surface(),
        species_by_dtk=species_by_dtk,
        zone_by_au=zone_by_au,
        max_initial_age=max_initial_age,
        scenario_workers=scenario_workers,
        policy_workers=policy_workers,
    )
    written = write_grid_record(record, out_dir)

    typer.echo(
        f"policy-grid complete ({record.n_policies} policies x "
        f"{record.n_scenarios} scenarios, {record.policy_workers} policy workers, "
        f"{record.scenario_workers} scenario workers):"
    )
    ok = [r for r in record.results if r.status == "ok"]
    for result in ok:
        samples = result.npv_samples
        mean = sum(samples) / len(samples) if samples else float("nan")
        typer.echo(f"  {result.policy.name:<36} NPV mean {mean:,.0f}  min {min(samples):,.0f}")
    failed = [r for r in record.results if r.status != "ok"]
    for result in failed:
        typer.echo(f"  {result.policy.name}: FAILED ({result.error})")
    for path in written:
        typer.echo(f"  wrote {path}")


@app.command("policy-rank")
def policy_rank_cmd(
    grid_summary: Path = typer.Option(
        ..., "--grid-summary", help="Grid run record (grid_summary.json from `policy-grid`)."
    ),
    fine_grid_summary: Path | None = typer.Option(
        None,
        "--fine-grid-summary",
        help="Optional fine-resolution grid record for the coarse-vs-fine sensitivity check.",
    ),
    criterion: str = typer.Option(
        "expected_npv_cvar", "--criterion", help="expected_npv_cvar | mean_cvar"
    ),
    weight: float | None = typer.Option(None, "--weight", min=0.0, max=1.0),
    alpha: float = typer.Option(0.95, "--alpha", min=0.0, max=1.0),
    out_dir: Path = typer.Option(
        Path("outputs") / "tsa29mini" / "policy_rank",
        "--out-dir",
        help="Directory for the ranking report (CSV/JSON, optional PNG).",
    ),
) -> None:
    """Rank grid policies and write the report (Phase 4, P4.4).

    Recomputes the per-policy risk metrics from a ``policy-grid``
    ``grid_summary.json`` (no re-solving), ranks under the given
    criterion, and writes ranking.csv / ranking.json / report.json plus a
    trade-off PNG when matplotlib is available.
    """
    from fresh_fuchs.economy.types import Provenance
    from fresh_fuchs.outer import (
        RankingCriterion,
        build_report,
        rank_from_grid_summary,
        write_report,
    )

    provenance = Provenance(
        source=f"policy-grid record {grid_summary}",
        as_of="2026-08-14",
        units="NPV (CAD)",
        basis=f"policy ranking, criterion {criterion}, alpha {alpha}",
    )
    criterion_enum = RankingCriterion(criterion)
    ranking = rank_from_grid_summary(
        grid_summary,
        criterion=criterion_enum,
        alpha=alpha,
        weight=weight,
        provenance=provenance,
    )
    fine_ranking = None
    if fine_grid_summary is not None:
        fine_ranking = rank_from_grid_summary(
            fine_grid_summary,
            criterion=criterion_enum,
            alpha=alpha,
            weight=weight,
            provenance=provenance,
        )
    report = build_report(
        ranking, name=grid_summary.stem, fine_ranking=fine_ranking, provenance=provenance
    )
    written = write_report(report, out_dir)

    typer.echo(f"policy-rank ({criterion}, alpha {alpha}):")
    for ranked in ranking.rankings:
        typer.echo(
            f"  {ranked.rank:>2}. {ranked.policy.name:<36} "
            f"E[NPV] {ranked.report.metrics.expected_npv:>12,.0f}  "
            f"CVaR {ranked.report.metrics.conditional_value_at_risk:>12,.0f}"
        )
    if report.sensitivity is not None:
        s = report.sensitivity
        typer.echo(
            f"sensitivity: coarse top '{s.coarse_top_policy}' -> fine top "
            f"'{s.fine_top_policy}' (stable: {s.top_rank_stable}, "
            f"E[NPV] delta {s.expected_npv_delta:,.0f}, CVaR delta {s.cvar_delta:,.0f})"
        )
    for path in written:
        typer.echo(f"  wrote {path}")


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
