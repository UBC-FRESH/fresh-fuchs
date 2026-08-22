"""Render the species-switching replant Quarto report.

Usage:
    python scripts/render_report.py                     # render with pre-computed CSVs
    python scripts/render_report.py --rerun             # re-run LP then render
    python scripts/render_report.py --policy comp_60    # specific policy
    python scripts/render_report.py --grid-dir tmp/grid  # custom grid dir
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = REPO_ROOT / "reports"


def render(
    *,
    rerun: bool = False,
    policy: str | None = None,
    grid_dir: Path | None = None,
) -> None:
    """Run the LP pipeline (if rerun) and render the Quarto report."""
    if rerun:
        _run_pipeline(grid_dir=grid_dir)

    if grid_dir is None:
        grid_dir = REPO_ROOT / "tmp" / "grid"

    cmd = [
        "quarto", "render",
        str(REPORTS_DIR / "replant_summary.qmd"),
    ]
    env_extra = {
        "FUCHS_GRID_DIR": str(grid_dir.resolve()),
    }
    if policy:
        env_extra["FUCHS_POLICY"] = policy

    import os
    env = {**os.environ, **env_extra}
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(REPO_ROOT), check=False, env=env)
    sys.exit(result.returncode)


def _run_pipeline(grid_dir: Path | None = None) -> None:
    """Run the replant LP example and write grid output to grid_dir."""
    import datetime

    from fresh_fuchs.economy.types import Provenance, interior_surface
    from fresh_fuchs.instance import InstanceConfig, SpeciesClass
    from fresh_fuchs.instance.synthetic import build_synthetic_areas, build_synthetic_yields
    from fresh_fuchs.instance.woodstock import write_woodstock_files
    from fresh_fuchs.outer.grid import (
        CompositionGridAxis,
        PolicyGrid,
        write_grid_record,
    )
    from fresh_fuchs.scenario import generate_scenarios
    from fresh_fuchs.scenario.distributions import (
        DistributionFamily,
        ParameterDistribution,
        UncertaintyDimension,
        UncertaintyVector,
    )
    from fresh_fuchs.scenario.records import ScenarioGenerationParams

    if grid_dir is None:
        grid_dir = REPO_ROOT / "tmp" / "grid"

    AU1, AU2 = 1, 2
    ZONE_BY_AU = {AU1: "SBPS", AU2: "IDF"}
    REPLANT_ACTIONS = ("harvest_SX", "harvest_FD")
    species_map = {
        ("29", "managed", "1", "natural", "baseline"): SpeciesClass.LODGEPOLE_PINE,
        ("29", "managed", "1", "planted", "baseline"): SpeciesClass.LODGEPOLE_PINE,
        ("29", "managed", "2", "natural", "baseline"): SpeciesClass.DOUGLAS_FIR,
        ("29", "unmanaged", "2", "natural", "baseline"): SpeciesClass.OTHER,
    }

    with tempfile.TemporaryDirectory() as tmp:
        config = InstanceConfig(
            model_name="replant-report",
            model_path=Path(tmp),
            horizon=3,
            period_length=10,
            max_age=300,
            min_harvest_age=60,
            max_harvest_age=300,
        )
        write_woodstock_files(
            areas=build_synthetic_areas(),
            yields=build_synthetic_yields(),
            config=config,
        )

        P = Provenance(source="report", as_of="T0", units="share", basis="report render")
        vector = UncertaintyVector(
            distributions={
                UncertaintyDimension.FIRE_BURN_RATE: ParameterDistribution(
                    name="burn_rate_multiplier",
                    family=DistributionFamily.GAUSSIAN,
                    provenance=P,
                    mean=1.0,
                    std=0.3,
                ),
                UncertaintyDimension.PRICE: ParameterDistribution(
                    name="price_factor",
                    family=DistributionFamily.FIXED,
                    provenance=P,
                    value=1.0,
                ),
            }
        )
        gen_params = ScenarioGenerationParams(
            n_scenarios=5,
            master_seed=42,
            horizon=config.horizon,
            period_length=config.period_length,
            zone_burn_rates={z: 0.01 for z in ZONE_BY_AU.values()},
            vector=vector,
            provenance=Provenance(
                source="report", as_of="T0", units="multiplier", basis="report render"
            ),
        )
        scenarios = generate_scenarios(gen_params)

        grid = PolicyGrid(
            name="replant-grid",
            composition_axes=(
                CompositionGridAxis(
                    species=SpeciesClass.SPRUCE,
                    values=(0.40, 0.60, 0.80),
                    tolerance=0.05,
                    provenance=P,
                ),
            ),
            include_unconstrained=True,
            provenance=P,
        )

        # Expand policies and patch replant_actions (grid.expand doesn't set it)
        from fresh_fuchs.scenario.pipeline import run_scenario_pipeline

        policies = [
            pol.model_copy(update={"replant_actions": REPLANT_ACTIONS})
            for pol in grid.expand()
        ]

        surface = interior_surface()
        results = []
        for pol in policies:
            try:
                run = run_scenario_pipeline(
                    scenarios=scenarios,
                    config=config,
                    surface=surface,
                    species_by_dtk=species_map,
                    zone_by_au=ZONE_BY_AU,
                    max_initial_age=300,
                    policy=pol,
                )
                from fresh_fuchs.outer.grid import PolicyGridResult
                results.append(PolicyGridResult(policy=pol, status="ok", run=run))
            except Exception as exc:
                results.append(PolicyGridResult(
                    policy=pol, status="failed", error=f"{type(exc).__name__}: {exc}",
                ))

        from fresh_fuchs.outer.grid import GridRunRecord, PolicyGridResult, _environment

        grid_record = GridRunRecord(
            name="replant-grid",
            n_policies=len(policies),
            n_scenarios=len(scenarios),
            master_seed=scenarios[0].seed if scenarios else 0,
            scenario_workers=1,
            policy_workers=1,
            run_at=datetime.datetime.now(datetime.UTC).isoformat(),
            environment=_environment(),
            results=tuple(results),
        )
        write_grid_record(grid_record, grid_dir)
        print(f"Grid written to {grid_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Render replant report")
    parser.add_argument("--rerun", action="store_true", help="Re-run LP before rendering")
    parser.add_argument("--policy", type=str, default=None, help="Policy name to show in detail")
    parser.add_argument("--grid-dir", type=Path, default=None, help="Path to grid output dir")
    args = parser.parse_args()
    render(rerun=args.rerun, policy=args.policy, grid_dir=args.grid_dir)


if __name__ == "__main__":
    main()
