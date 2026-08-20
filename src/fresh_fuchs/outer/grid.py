"""Outer policy grid-search driver (Phase 4, P4.2).

A ``PolicyGrid`` declares the search axes: composition axes (candidate
area-share targets per species group, each with a tolerance) and one
harvest axis (candidate AAC levels in ``aac_proxy`` mode, or candidate
rotation-age floors/ceilings per species in ``rotation_constraints``
mode). ``expand`` takes the Cartesian product into ``PolicyRecord``
points. ``run_grid`` evaluates every point as one full-MC run (all
scenarios through the P3.5 scenario -> inner-LP pipeline under the
P4.1 policy rows); policies can be evaluated in a process pool (spawn),
and each policy's scenario solves remain deterministic, so parallel
results bit-match the sequential run.
"""

from __future__ import annotations

import datetime
import itertools
import json
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Annotated, Any

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator

from fresh_fuchs.economy.npv import DevelopmentTypeKey
from fresh_fuchs.economy.types import EconomicSurface, Provenance
from fresh_fuchs.instance import InstanceConfig
from fresh_fuchs.instance.species import SpeciesClass
from fresh_fuchs.outer.records import (
    CompositionTarget,
    HarvestPolicy,
    HarvestPolicyMode,
    PolicyRecord,
)
from fresh_fuchs.scenario.pipeline import (
    PipelineRunRecord,
    _environment,
    run_scenario_pipeline,
)
from fresh_fuchs.scenario.records import DisturbanceScenario


class CompositionGridAxis(BaseModel):
    """One composition axis: candidate area-share targets for a species."""

    model_config = ConfigDict(frozen=True)

    species: SpeciesClass
    values: tuple[float, ...]
    tolerance: Annotated[float, Field(ge=0.0, lt=1.0)] = 0.05
    provenance: Provenance

    @model_validator(mode="after")
    def _require_values(self) -> CompositionGridAxis:
        if not self.values:
            raise ValueError("composition axis requires at least one candidate value")
        if any(not 0.0 <= v <= 1.0 for v in self.values):
            raise ValueError("composition candidate shares must be in [0, 1]")
        return self


class HarvestGridAxis(BaseModel):
    """One harvest axis: candidate AAC levels or rotation-age values.

    In ``rotation_constraints`` mode ``species`` selects the species the
    axis applies to and ``ceiling`` selects floor (default) vs ceiling.
    """

    model_config = ConfigDict(frozen=True)

    mode: HarvestPolicyMode
    values: tuple[float, ...]
    species: SpeciesClass | None = None
    ceiling: bool = False
    tolerance: Annotated[float, Field(ge=0.0, lt=1.0)] = 0.05
    provenance: Provenance

    @model_validator(mode="after")
    def _validate_axis(self) -> HarvestGridAxis:
        if not self.values:
            raise ValueError("harvest axis requires at least one candidate value")
        if self.mode is HarvestPolicyMode.AAC_PROXY:
            if any(v <= 0.0 for v in self.values):
                raise ValueError("aac_proxy candidate levels must be positive")
            if self.species is not None or self.ceiling:
                raise ValueError("species/ceiling apply only to rotation axes")
        if self.mode is HarvestPolicyMode.ROTATION_CONSTRAINTS:
            if self.species is None:
                raise ValueError("rotation axis requires a species")
            if any(v < 0 for v in self.values):
                raise ValueError("rotation ages must be non-negative")
        return self


class PolicyGrid(BaseModel):
    """Cartesian grid over composition axes and one harvest axis.

    Two modes for specifying composition targets:

    - **Axis mode** (``composition_axes``): per-species axes with candidate
      share values; ``expand`` takes the Cartesian product.
    - **Points mode** (``composition_points``): an explicit list of
      species→share mappings; no Cartesian product, each point is taken
      as-is.  Use this when only certain combinations are feasible or
      meaningful.

    ``composition_points`` takes precedence when both are provided.
    ``composition_tolerance`` is the default tolerance for points mode
    (overridable per-point with a ``tolerance`` key).

    With ``include_unconstrained`` the fully unconstrained policy (no
    composition targets, no harvest policy) is prepended as a baseline
    reference point.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    composition_axes: tuple[CompositionGridAxis, ...] = Field(default_factory=tuple)
    composition_points: tuple[dict[str, float], ...] = Field(
        default_factory=tuple,
        description=(
            "Explicit species→share mappings. Each dict maps species codes "
            "(e.g. 'PL', 'FD') to target area shares. Overrides "
            "composition_axes when non-empty."
        ),
    )
    composition_tolerance: Annotated[float, Field(ge=0.0, lt=1.0)] = Field(
        default=0.05,
        description=(
            "Default tolerance for composition_points (can be overridden "
            "per-point with a 'tolerance' key)."
        ),
    )
    harvest_axis: HarvestGridAxis | None = None
    include_unconstrained: bool = False
    provenance: Provenance

    def expand(self) -> tuple[PolicyRecord, ...]:
        """Expand the grid into its Cartesian product of policies.

        Deterministic order: composition points/axes in declaration order,
        then the harvest axis; the unconstrained point (if requested) comes
        first.
        """
        harvest_cells = [None]
        if self.harvest_axis is not None:
            harvest_cells = list(self.harvest_axis.values)

        points: list[PolicyRecord] = []
        if self.include_unconstrained:
            points.append(
                PolicyRecord(
                    name=f"{self.name}_unconstrained",
                    composition_targets=(),
                    harvest_policy=None,
                    provenance=self.provenance,
                )
            )

        if self.composition_points:
            comp_cells = self._expand_composition_points()
        elif self.composition_axes:
            comp_cells = [
                self._expand_axes_cell(cell)
                for cell in itertools.product(*[axis.values for axis in self.composition_axes])
            ]
        else:
            comp_cells = [((), "")]

        for targets, label in comp_cells:
            for level in harvest_cells:
                harvest_policy = None
                if self.harvest_axis is not None:
                    harvest_policy = _harvest_policy_for(self.harvest_axis, level)
                points.append(
                    PolicyRecord(
                        name=_point_name_from_label(self.name, label, self.harvest_axis, level),
                        composition_targets=targets,
                        harvest_policy=harvest_policy,
                        provenance=self.provenance,
                    )
                )
        return tuple(points)

    def _expand_composition_points(
        self,
    ) -> list[tuple[tuple[CompositionTarget, ...], str]]:
        """Convert composition_points into (targets, label) pairs."""
        result: list[tuple[tuple[CompositionTarget, ...], str]] = []
        for point in self.composition_points:
            tolerance = point.get("tolerance", self.composition_tolerance)
            targets: list[CompositionTarget] = []
            parts: list[str] = []
            for species_str, share in point.items():
                if species_str == "tolerance":
                    continue
                species = SpeciesClass(species_str)
                targets.append(
                    CompositionTarget(
                        species=species,
                        target_share=share,
                        tolerance=tolerance,
                        provenance=self.provenance,
                    )
                )
                parts.append(f"{species.value}_{share:.2f}")
            result.append((tuple(targets), "_".join(parts)))
        return result

    def _expand_axes_cell(
        self, cell: tuple[float, ...]
    ) -> tuple[tuple[CompositionTarget, ...], str]:
        """Convert a Cartesian-product cell from composition_axes into (targets, label)."""
        targets = tuple(
            CompositionTarget(
                species=axis.species,
                target_share=value,
                tolerance=axis.tolerance,
                provenance=axis.provenance,
            )
            for axis, value in zip(self.composition_axes, cell)
        )
        label = "_".join(
            f"{axis.species.value}_{value:.2f}"
            for axis, value in zip(self.composition_axes, cell)
        )
        return targets, label


def _harvest_policy_for(axis: HarvestGridAxis, level: float) -> HarvestPolicy:
    if axis.mode is HarvestPolicyMode.AAC_PROXY:
        return HarvestPolicy(
            mode=HarvestPolicyMode.AAC_PROXY,
            aac_level_m3_per_yr=level,
            aac_tolerance=axis.tolerance,
            provenance=axis.provenance,
        )
    species = axis.species
    assert species is not None
    if axis.ceiling:
        return HarvestPolicy(
            mode=HarvestPolicyMode.ROTATION_CONSTRAINTS,
            rotation_ceiling={species: int(level)},
            provenance=axis.provenance,
        )
    return HarvestPolicy(
        mode=HarvestPolicyMode.ROTATION_CONSTRAINTS,
        rotation_floor={species: int(level)},
        provenance=axis.provenance,
    )


def _point_name_from_label(
    grid_name: str,
    comp_label: str,
    harvest_axis: HarvestGridAxis | None,
    level: float | None,
) -> str:
    """Compose a policy name from the grid name, composition label, and harvest level."""
    parts = [grid_name]
    if comp_label:
        parts.append(comp_label)
    if harvest_axis is not None and level is not None:
        if harvest_axis.mode is HarvestPolicyMode.AAC_PROXY:
            parts.append(f"aac_{level:.0f}")
        elif harvest_axis.ceiling:
            parts.append(f"{harvest_axis.species.value}_ceil_{int(level)}")
        else:
            parts.append(f"{harvest_axis.species.value}_floor_{int(level)}")
    return "_".join(parts)


class PolicyGridResult(BaseModel):
    """One grid point evaluation: the policy and its full-MC run record.

    ``status`` is ``ok`` on success; a failing or infeasible point keeps
    ``run`` unset and records the exception in ``error`` so one bad point
    does not sink the grid.
    """

    model_config = ConfigDict(frozen=True)

    policy: PolicyRecord
    status: str = Field(description="'ok' or 'failed'.")
    run: PipelineRunRecord | None = None
    error: str | None = None

    @property
    def npv_samples(self) -> tuple[float, ...]:
        if self.run is None:
            return ()
        return tuple(record.npv for record in self.run.scenarios)


class GridRunRecord(BaseModel):
    """A full grid evaluation: per-policy results plus run provenance."""

    name: str
    n_policies: int
    n_scenarios: int
    master_seed: int
    scenario_workers: int
    policy_workers: int
    run_at: str
    environment: dict[str, str]
    results: tuple[PolicyGridResult, ...]


def _grid_policy_worker(
    payload: tuple[
        PolicyRecord,
        list[DisturbanceScenario],
        InstanceConfig,
        EconomicSurface,
        dict[DevelopmentTypeKey, SpeciesClass],
        dict[int, str],
        int,
        int,
        int,
    ],
) -> PolicyGridResult:
    (
        policy,
        scenarios,
        config,
        surface,
        species_by_dtk,
        zone_by_au,
        max_initial_age,
        min_salvage_age,
        scenario_workers,
    ) = payload
    try:
        run = run_scenario_pipeline(
            scenarios=scenarios,
            config=config,
            surface=surface,
            species_by_dtk=species_by_dtk,
            zone_by_au=zone_by_au,
            max_initial_age=max_initial_age,
            min_salvage_age=min_salvage_age,
            n_workers=scenario_workers,
            policy=policy,
        )
        return PolicyGridResult(policy=policy, status="ok", run=run)
    except Exception as exc:  # noqa: BLE001 - grid must surface, not crash
        return PolicyGridResult(
            policy=policy,
            status="failed",
            error=f"{type(exc).__name__}: {exc}",
        )


def run_grid(
    *,
    grid: PolicyGrid,
    scenarios: list[DisturbanceScenario],
    config: InstanceConfig,
    surface: EconomicSurface,
    species_by_dtk: dict[DevelopmentTypeKey, SpeciesClass],
    zone_by_au: dict[int, str],
    max_initial_age: int = 436,
    min_salvage_age: int = 60,
    scenario_workers: int = 1,
    policy_workers: int = 1,
) -> GridRunRecord:
    """Evaluate every grid point as one full-MC run.

    Policies are distributed over a spawn process pool when
    ``policy_workers > 1``; each policy's scenario solves are independent
    and seed-fixed, so parallel results bit-match the sequential run.
    """
    points = grid.expand()
    kwargs = dict(
        scenarios=scenarios,
        config=config,
        surface=surface,
        species_by_dtk=species_by_dtk,
        zone_by_au=zone_by_au,
        max_initial_age=max_initial_age,
        min_salvage_age=min_salvage_age,
        scenario_workers=scenario_workers,
    )
    results: list[PolicyGridResult]
    if policy_workers <= 1:
        results = [_grid_policy_worker((policy, *kwargs.values())) for policy in points]
    else:
        payloads = [(policy, *kwargs.values()) for policy in points]
        with ProcessPoolExecutor(
            max_workers=policy_workers, mp_context=multiprocessing.get_context("spawn")
        ) as executor:
            results = list(executor.map(_grid_policy_worker, payloads))
    return GridRunRecord(
        name=grid.name,
        n_policies=len(points),
        n_scenarios=len(scenarios),
        master_seed=scenarios[0].seed if scenarios else 0,
        scenario_workers=scenario_workers,
        policy_workers=policy_workers,
        run_at=datetime.datetime.now(datetime.UTC).isoformat(),
        environment=_environment(),
        results=tuple(results),
    )


def write_grid_record(record: GridRunRecord, out_dir: Path) -> list[Path]:
    """Write per-policy pipeline records plus grid-level summaries.

    Returns the list of written paths. Layout::

        out_dir/<policy_name>/pipeline_run.json   (per-policy run record)
        out_dir/<policy_name>/scenario_%04d_schedule.csv
        out_dir/<policy_name>/pipeline_summary.csv
        out_dir/grid_summary.csv                  (per-policy NPV rows)
        out_dir/grid_summary.json                 (machine-readable grid)
    """
    from fresh_fuchs.scenario.pipeline import write_pipeline_record

    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for result in record.results:
        policy_dir = out_dir / result.policy.name
        if result.run is not None:
            written.extend(write_pipeline_record(result.run, policy_dir))
        else:
            policy_dir.mkdir(parents=True, exist_ok=True)
            error_path = policy_dir / "error.txt"
            error_path.write_text(result.error or "")
            written.append(error_path)

    rows = []
    for result in record.results:
        row: dict[str, Any] = {
            "policy": result.policy.name,
            "status": result.status,
            "npv_samples": list(result.npv_samples),
            "mean_npv": sum(result.npv_samples) / len(result.npv_samples)
            if result.npv_samples
            else None,
            "min_npv": min(result.npv_samples) if result.npv_samples else None,
            "max_npv": max(result.npv_samples) if result.npv_samples else None,
            "mean_annual_harvest_m3_per_yr": None,
        }
        if result.run is not None:
            row["mean_annual_harvest_m3_per_yr"] = sum(
                s.mean_annual_harvest_m3_per_yr for s in result.run.scenarios
            ) / len(result.run.scenarios)
        rows.append(row)

    summary_df = pd.DataFrame(rows)
    if not summary_df.empty:
        samples = summary_df.pop("npv_samples")
        for i in range(record.n_scenarios):
            summary_df[f"npv_{i}"] = [values[i] if i < len(values) else None for values in samples]
    summary_path = out_dir / "grid_summary.csv"
    summary_df.to_csv(summary_path, index=False)
    written.append(summary_path)

    summary_json = {
        "name": record.name,
        "n_policies": record.n_policies,
        "n_scenarios": record.n_scenarios,
        "master_seed": record.master_seed,
        "scenario_workers": record.scenario_workers,
        "policy_workers": record.policy_workers,
        "run_at": record.run_at,
        "environment": record.environment,
        "results": [
            {
                "policy": result.policy.model_dump(mode="json"),
                "status": result.status,
                "npv_samples": list(result.npv_samples),
                "error": result.error,
            }
            for result in record.results
        ],
    }
    json_path = out_dir / "grid_summary.json"
    json_path.write_text(json.dumps(summary_json, indent=2, sort_keys=True))
    written.append(json_path)
    return written


__all__ = [
    "CompositionGridAxis",
    "GridRunRecord",
    "HarvestGridAxis",
    "PolicyGrid",
    "PolicyGridResult",
    "run_grid",
    "write_grid_record",
]
