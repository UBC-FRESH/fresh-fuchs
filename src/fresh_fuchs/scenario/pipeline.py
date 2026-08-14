"""Scenario -> inner-LP pipeline (Phase 3, P3.5).

Runs the fire-aware Model I LP once per scenario (full foresight): each
scenario is encoded into a fresh inner LP (:mod:`fresh_fuchs.scenario
.fire_lp`), solved, applied, and recorded with its schedule and NPV.
Scenarios can be solved in a process pool; the per-scenario solves are
deterministic (fixed seeds, no shared RNG), so parallel results bit-match
the sequential run for the same catalogue.
"""

from __future__ import annotations

import datetime
import json
import multiprocessing
import platform
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import pandas as pd
import ws3
from pydantic import BaseModel, Field

import fresh_fuchs
from fresh_fuchs.economy.npv import DevelopmentTypeKey
from fresh_fuchs.economy.types import EconomicSurface
from fresh_fuchs.instance import (
    InstanceConfig,
    bootstrap_model,
    prepare_optimization,
    summarize,
)
from fresh_fuchs.instance.species import SpeciesClass
from fresh_fuchs.outer.records import HarvestPolicyMode
from fresh_fuchs.scenario.fire_lp import (
    FireLpConfig,
    add_fire_problem,
    add_salvage_action,
    apply_salvage_operability,
    solve_fire_lp,
)
from fresh_fuchs.scenario.records import DisturbanceScenario

SOLVER = "ws3 opt default (HiGHS)"


class ScenarioRunPeriod(BaseModel):
    """One period of a scenario's applied schedule (m3, ha)."""

    period: int
    harvest_area_ha: float
    harvest_volume_m3: float
    salvage_area_ha: float
    salvage_volume_m3: float
    salvageable_volume_m3: float
    growing_stock_m3: float


class ScenarioRunRecord(BaseModel):
    """LP result for one scenario: schedule, NPV, and provenance."""

    scenario: DisturbanceScenario
    status: str = Field(description="Solver status (e.g. 'optimal').")
    npv: float = Field(description="Total discounted NPV of the scenario LP (CAD).")
    total_harvested_area_ha: float
    total_harvested_volume_m3: float
    mean_annual_harvest_m3_per_yr: float
    periods: tuple[ScenarioRunPeriod, ...] = Field(description="Per-period schedule.")


class PipelineRunRecord(BaseModel):
    """A full scenario->LP run: per-scenario records plus environment."""

    n_scenarios: int
    n_workers: int
    master_seed: int
    run_at: str
    environment: dict[str, str] = Field(
        description="Python/fresh-fuchs/ws3/solver versions captured for provenance."
    )
    scenarios: tuple[ScenarioRunRecord, ...]


def _run_scenario_worker(
    payload: tuple[
        InstanceConfig,
        DisturbanceScenario,
        EconomicSurface,
        dict[DevelopmentTypeKey, SpeciesClass],
        dict[int, str],
        int,
        int,
        Any,
    ],
) -> ScenarioRunRecord:
    (
        config,
        scenario,
        surface,
        species_by_dtk,
        zone_by_au,
        max_initial_age,
        min_salvage_age,
        policy,
    ) = payload
    return run_scenario_lp(
        config=config,
        scenario=scenario,
        surface=surface,
        species_by_dtk=species_by_dtk,
        zone_by_au=zone_by_au,
        max_initial_age=max_initial_age,
        min_salvage_age=min_salvage_age,
        policy=policy,
    )


def run_scenario_lp(
    *,
    config: InstanceConfig,
    scenario: DisturbanceScenario,
    surface: EconomicSurface,
    species_by_dtk: dict[DevelopmentTypeKey, SpeciesClass],
    zone_by_au: dict[int, str],
    max_initial_age: int = 436,
    min_salvage_age: int = 60,
    policy: Any | None = None,
) -> ScenarioRunRecord:
    """Build, solve, and apply the inner LP for one scenario (full foresight).

    The model is bootstrapped fresh per scenario (cheap) because the salvage
    action/operability mutate the model; the expensive Model I tree build is
    scenario-specific and parallelized by the pipeline runner. With
    ``policy`` (an outer ``PolicyRecord``), rotation constraints are applied
    before the tree build and the policy's general rows are folded into the
    fire LP.
    """
    model = prepare_optimization(
        bootstrap_model(config), max_initial_age=max_initial_age, config=config
    )
    model = add_salvage_action(model, max_age=config.max_age, min_salvage_age=min_salvage_age)
    model = apply_salvage_operability(model, scenario=scenario, zone_by_au=zone_by_au)
    if policy is not None and policy.harvest_policy is not None:
        if policy.harvest_policy.mode is HarvestPolicyMode.ROTATION_CONSTRAINTS:
            from fresh_fuchs.outer.policy import apply_rotation_constraints

            model = apply_rotation_constraints(model, policy=policy, species_by_dtk=species_by_dtk)
    fire_config = FireLpConfig(workers=1, zone_by_au=zone_by_au, min_salvage_age=min_salvage_age)
    problem = add_fire_problem(
        model,
        fire_config,
        scenario=scenario,
        surface=surface,
        species_by_dtk=species_by_dtk,
        policy=policy,
    )
    results = solve_fire_lp(model, problem, scenario=scenario, config=fire_config)
    status = problem.status()
    summary = summarize(results, period_length=config.period_length)
    return ScenarioRunRecord(
        scenario=scenario,
        status=status,
        npv=float(problem.z()),
        total_harvested_area_ha=summary["total_harvested_area_ha"],
        total_harvested_volume_m3=summary["total_harvested_volume_m3"],
        mean_annual_harvest_m3_per_yr=summary["mean_annual_harvest_m3_per_yr"],
        periods=tuple(
            ScenarioRunPeriod(
                period=int(row.period),
                harvest_area_ha=float(row.harvest_area_ha),
                harvest_volume_m3=float(row.harvest_volume_m3),
                salvage_area_ha=float(row.salvage_area_ha),
                salvage_volume_m3=float(row.salvage_volume_m3),
                salvageable_volume_m3=float(row.salvageable_volume_m3),
                growing_stock_m3=float(row.growing_stock_m3),
            )
            for row in results.itertuples(index=False)
        ),
    )


def _environment() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "fresh_fuchs": fresh_fuchs.__version__,
        "ws3": getattr(ws3, "__version__", "unknown"),
        "solver": SOLVER,
    }


def run_scenario_pipeline(
    *,
    scenarios: list[DisturbanceScenario],
    config: InstanceConfig,
    surface: EconomicSurface,
    species_by_dtk: dict[DevelopmentTypeKey, SpeciesClass],
    zone_by_au: dict[int, str],
    max_initial_age: int = 436,
    min_salvage_age: int = 60,
    n_workers: int = 1,
    policy: Any | None = None,
) -> PipelineRunRecord:
    """Run the inner LP once per scenario, sequential or process-pool.

    With ``n_workers > 1`` scenarios are distributed over a process pool
    created with the ``spawn`` start method: the parent process is typically
    multi-threaded (solver/OpenMP state), and forking it would be unsafe.
    Because each scenario is solved from its own fresh model under fixed
    seeds, parallel results are bit-identical to the sequential run. With
    ``policy``, the outer policy constraints are applied to every scenario.
    """
    kwargs = dict(
        config=config,
        surface=surface,
        species_by_dtk=species_by_dtk,
        zone_by_au=zone_by_au,
        max_initial_age=max_initial_age,
        min_salvage_age=min_salvage_age,
        policy=policy,
    )
    records: list[ScenarioRunRecord]
    if n_workers <= 1:
        records = [run_scenario_lp(scenario=scenario, **kwargs) for scenario in scenarios]
    else:
        payloads = [
            (
                config,
                scenario,
                surface,
                species_by_dtk,
                zone_by_au,
                max_initial_age,
                min_salvage_age,
                policy,
            )
            for scenario in scenarios
        ]
        with ProcessPoolExecutor(
            max_workers=n_workers, mp_context=multiprocessing.get_context("spawn")
        ) as executor:
            records = list(executor.map(_run_scenario_worker, payloads))
    master_seed = scenarios[0].seed if scenarios else 0
    return PipelineRunRecord(
        n_scenarios=len(scenarios),
        n_workers=n_workers,
        master_seed=master_seed,
        run_at=datetime.datetime.now(datetime.UTC).isoformat(),
        environment=_environment(),
        scenarios=tuple(records),
    )


def write_pipeline_record(record: PipelineRunRecord, out_dir: Path) -> list[Path]:
    """Write the pipeline run record: JSON + one schedule CSV per scenario."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    payload = record.model_dump(mode="json")
    record_path = out_dir / "pipeline_run.json"
    record_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    written.append(record_path)
    for i, scenario_record in enumerate(record.scenarios):
        rows = [period.model_dump(mode="json") for period in scenario_record.periods]
        csv_path = out_dir / f"scenario_{i:04d}_schedule.csv"
        pd.DataFrame(rows).to_csv(csv_path, index=False)
        written.append(csv_path)
    summary = pd.DataFrame(
        [
            {
                "scenario": record.scenarios[i].scenario.name,
                "seed": record.scenarios[i].scenario.seed,
                "status": record.scenarios[i].status,
                "npv": record.scenarios[i].npv,
                "total_harvested_area_ha": record.scenarios[i].total_harvested_area_ha,
                "total_harvested_volume_m3": record.scenarios[i].total_harvested_volume_m3,
                "mean_annual_harvest_m3_per_yr": record.scenarios[i].mean_annual_harvest_m3_per_yr,
            }
            for i in range(len(record.scenarios))
        ]
    )
    summary_path = out_dir / "pipeline_summary.csv"
    summary.to_csv(summary_path, index=False)
    written.append(summary_path)
    return written


__all__ = [
    "PipelineRunRecord",
    "ScenarioRunPeriod",
    "ScenarioRunRecord",
    "run_scenario_lp",
    "run_scenario_pipeline",
    "write_pipeline_record",
]
