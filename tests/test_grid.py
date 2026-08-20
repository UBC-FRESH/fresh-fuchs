"""Outer policy grid driver tests (P4.2): expansion, evaluation, parallelism."""

from __future__ import annotations

from pathlib import Path

from fresh_fuchs.economy import interior_surface
from fresh_fuchs.economy.types import Provenance
from fresh_fuchs.instance import InstanceConfig
from fresh_fuchs.instance.species import SpeciesClass
from fresh_fuchs.instance.woodstock import write_woodstock_files
from fresh_fuchs.outer import (
    CompositionGridAxis,
    HarvestGridAxis,
    PolicyGrid,
    run_grid,
    write_grid_record,
)
from fresh_fuchs.outer.records import HarvestPolicyMode
from fresh_fuchs.scenario.distributions import (
    DistributionFamily,
    ParameterDistribution,
    UncertaintyDimension,
    UncertaintyVector,
)
from fresh_fuchs.scenario.fire import DEFAULT_SEVERITY
from fresh_fuchs.scenario.records import ScenarioGenerationParams, generate_scenarios

P = Provenance(source="test", as_of="T0", units="multiplier", basis="test grid")

ZONE_RATES = {"IDF": 0.005, "SBPS": 0.01}

ZONE_BY_AU = {1: "SBPS", 2: "IDF"}


def _species_map() -> dict:
    return {
        ("29", "managed", "1", "natural", "baseline"): SpeciesClass.LODGEPOLE_PINE,
        ("29", "managed", "1", "planted", "baseline"): SpeciesClass.LODGEPOLE_PINE,
        ("29", "managed", "2", "natural", "baseline"): SpeciesClass.DOUGLAS_FIR,
        ("29", "unmanaged", "2", "natural", "baseline"): SpeciesClass.OTHER,
    }


def _params(n_scenarios: int = 3, master_seed: int = 7) -> ScenarioGenerationParams:
    vector = UncertaintyVector(
        distributions={
            UncertaintyDimension.FIRE_BURN_RATE: ParameterDistribution(
                name="burn_rate_multiplier",
                family=DistributionFamily.GAUSSIAN,
                provenance=P,
                mean=1.0,
                std=0.2,
            ),
            UncertaintyDimension.PRICE: ParameterDistribution(
                name="price_factor",
                family=DistributionFamily.FIXED,
                provenance=P,
                value=1.0,
            ),
        }
    )
    return ScenarioGenerationParams(
        n_scenarios=n_scenarios,
        master_seed=master_seed,
        horizon=2,
        period_length=10,
        zone_burn_rates=ZONE_RATES,
        vector=vector,
        severity=DEFAULT_SEVERITY,
        provenance=P,
    )


def _scenarios(n: int = 3) -> list:
    return generate_scenarios(_params(n_scenarios=n))


def _model_context(tmp_path: Path):
    from tests.conftest import build_synthetic_areas, build_synthetic_yields

    config = InstanceConfig(
        model_name="synthetic",
        model_path=tmp_path,
        horizon=2,
        period_length=10,
        max_age=300,
        min_harvest_age=60,
    )
    write_woodstock_files(
        areas=build_synthetic_areas(), yields=build_synthetic_yields(), config=config
    )
    return config, _species_map()


def _grid(**overrides) -> PolicyGrid:
    defaults = dict(
        name="g",
        composition_axes=(
            CompositionGridAxis(
                species=SpeciesClass.LODGEPOLE_PINE,
                values=(0.85,),
                tolerance=0.05,
                provenance=P,
            ),
        ),
        harvest_axis=HarvestGridAxis(
            mode=HarvestPolicyMode.AAC_PROXY,
            values=(1_200.0,),
            tolerance=0.05,
            provenance=P,
        ),
        provenance=P,
    )
    defaults.update(overrides)
    return PolicyGrid(**defaults)


def _run_kw(tmp_path):
    config, species_by_dtk = _model_context(tmp_path)
    return dict(
        scenarios=_scenarios(3),
        config=config,
        surface=interior_surface(),
        species_by_dtk=species_by_dtk,
        zone_by_au=ZONE_BY_AU,
        max_initial_age=300,
    )


def test_grid_expands_cartesian_product() -> None:
    grid = PolicyGrid(
        name="prod",
        composition_axes=(
            CompositionGridAxis(
                species=SpeciesClass.LODGEPOLE_PINE,
                values=(0.8, 0.9),
                tolerance=0.05,
                provenance=P,
            ),
            CompositionGridAxis(
                species=SpeciesClass.DOUGLAS_FIR,
                values=(0.1,),
                tolerance=0.05,
                provenance=P,
            ),
        ),
        harvest_axis=HarvestGridAxis(
            mode=HarvestPolicyMode.AAC_PROXY,
            values=(1_000.0, 2_000.0),
            tolerance=0.05,
            provenance=P,
        ),
        include_unconstrained=True,
        provenance=P,
    )
    points = grid.expand()
    assert len(points) == 1 + 2 * 1 * 2  # unconstrained + 2 comp x 1 comp x 2 aac
    assert points[0].name == "prod_unconstrained"
    assert points[0].composition_targets == ()
    assert points[0].harvest_policy is None
    names = [p.name for p in points]
    assert len(set(names)) == len(names)
    constrained = points[1:]
    for p in constrained:
        assert len(p.composition_targets) == 2
        assert p.harvest_policy is not None
        assert p.harvest_policy.mode is HarvestPolicyMode.AAC_PROXY
    assert {p.composition_targets[0].target_share for p in constrained} == {0.8, 0.9}
    assert {p.harvest_policy.aac_level_m3_per_yr for p in constrained} == {1_000.0, 2_000.0}


def test_grid_expand_rotation_axis() -> None:
    grid = PolicyGrid(
        name="rot",
        harvest_axis=HarvestGridAxis(
            mode=HarvestPolicyMode.ROTATION_CONSTRAINTS,
            species=SpeciesClass.LODGEPOLE_PINE,
            values=(100.0, 140.0),
            provenance=P,
        ),
        provenance=P,
    )
    points = grid.expand()
    assert len(points) == 2
    assert points[0].harvest_policy.rotation_floor == {SpeciesClass.LODGEPOLE_PINE: 100}
    assert points[1].harvest_policy.rotation_floor == {SpeciesClass.LODGEPOLE_PINE: 140}


def test_grid_axis_validation() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        CompositionGridAxis(species=SpeciesClass.LODGEPOLE_PINE, values=(1.5,), provenance=P)
    with pytest.raises(ValidationError):
        HarvestGridAxis(mode=HarvestPolicyMode.AAC_PROXY, values=(0.0,), provenance=P)
    with pytest.raises(ValidationError):
        HarvestGridAxis(
            mode=HarvestPolicyMode.ROTATION_CONSTRAINTS,
            values=(140.0,),
            provenance=P,
        )


def test_run_grid_evaluates_every_point(tmp_path):
    kw = _run_kw(tmp_path)
    record = run_grid(grid=_grid(), **kw)
    assert record.n_policies == 1
    assert record.n_scenarios == 3
    result = record.results[0]
    assert result.status == "ok"
    assert result.run is not None
    assert len(result.npv_samples) == 3
    assert all(s == "optimal" for s in (r.status for r in result.run.scenarios))
    samples = result.npv_samples
    assert len(set(samples)) > 1  # scenarios differ


def test_run_grid_seed_fixed_bit_stable(tmp_path):
    kw = _run_kw(tmp_path)
    grid = _grid(include_unconstrained=True)
    first = run_grid(grid=grid, **kw)
    second = run_grid(grid=grid, **kw)
    assert first.n_policies == second.n_policies == 2
    for left, right in zip(first.results, second.results):
        assert left.status == right.status
        assert left.npv_samples == right.npv_samples


def test_run_grid_parallel_bit_matches_sequential(tmp_path):
    kw = _run_kw(tmp_path)
    grid = _grid(
        composition_axes=(
            CompositionGridAxis(
                species=SpeciesClass.LODGEPOLE_PINE,
                values=(0.85, 0.9),
                tolerance=0.05,
                provenance=P,
            ),
        ),
        harvest_axis=HarvestGridAxis(
            mode=HarvestPolicyMode.AAC_PROXY,
            values=(1_200.0, 1_400.0),
            tolerance=0.05,
            provenance=P,
        ),
    )
    sequential = run_grid(grid=grid, policy_workers=1, **kw)
    parallel = run_grid(grid=grid, policy_workers=2, **kw)
    assert sequential.n_policies == 4
    assert sequential.results[0].policy.name == parallel.results[0].policy.name
    for left, right in zip(sequential.results, parallel.results):
        assert left.status == right.status
        assert left.npv_samples == right.npv_samples


def test_run_grid_failed_policy_recorded_not_crashing(tmp_path):
    kw = _run_kw(tmp_path)
    grid = PolicyGrid(
        name="infeas",
        harvest_axis=HarvestGridAxis(
            mode=HarvestPolicyMode.AAC_PROXY,
            values=(40_000.0,),
            tolerance=0.0,
            provenance=P,
        ),
        provenance=P,
    )
    record = run_grid(grid=grid, **kw)
    result = record.results[0]
    assert result.status == "failed"
    assert result.run is None
    assert result.error


def test_write_grid_record_writes_summaries_and_per_policy(tmp_path):
    kw = _run_kw(tmp_path)
    record = run_grid(grid=_grid(include_unconstrained=True), **kw)
    out = tmp_path / "grid"
    written = write_grid_record(record, out)
    assert (out / "grid_summary.csv").exists()
    assert (out / "grid_summary.json").exists()
    policy_dir = out / record.results[0].policy.name
    assert (policy_dir / "pipeline_run.json").exists()
    assert (policy_dir / "pipeline_summary.csv").exists()
    assert all(path.exists() for path in written)
    summary = (out / "grid_summary.csv").read_text().splitlines()
    assert len(summary) == record.n_policies + 1
    assert "npv_0" in summary[0]


def test_grid_expand_composition_points() -> None:
    grid = PolicyGrid(
        name="pts",
        composition_points=(
            {"PL": 0.70, "FD": 0.20},
            {"PL": 0.60, "FD": 0.30},
        ),
        composition_tolerance=0.05,
        harvest_axis=HarvestGridAxis(
            mode=HarvestPolicyMode.AAC_PROXY,
            values=(1_000.0,),
            tolerance=0.05,
            provenance=P,
        ),
        provenance=P,
    )
    points = grid.expand()
    assert len(points) == 2
    assert points[0].name == "pts_PL_0.70_FD_0.20_aac_1000"
    assert points[1].name == "pts_PL_0.60_FD_0.30_aac_1000"
    for p in points:
        assert len(p.composition_targets) == 2
        assert p.harvest_policy is not None
    pl_shares = {p.composition_targets[0].target_share for p in points}
    assert pl_shares == {0.70, 0.60}
    for p in points:
        for t in p.composition_targets:
            assert t.tolerance == 0.05


def test_grid_expand_composition_points_with_unconstrained() -> None:
    grid = PolicyGrid(
        name="pts",
        composition_points=(
            {"PL": 0.80, "FD": 0.10},
        ),
        include_unconstrained=True,
        provenance=P,
    )
    points = grid.expand()
    assert len(points) == 2
    assert points[0].name == "pts_unconstrained"
    assert points[0].composition_targets == ()
    assert points[1].name == "pts_PL_0.80_FD_0.10"
    assert len(points[1].composition_targets) == 2


def test_grid_expand_composition_points_per_point_tolerance() -> None:
    grid = PolicyGrid(
        name="pts",
        composition_points=(
            {"PL": 0.70, "FD": 0.20},
            {"PL": 0.60, "FD": 0.30, "tolerance": 0.03},
        ),
        composition_tolerance=0.05,
        provenance=P,
    )
    points = grid.expand()
    assert len(points) == 2
    for t in points[0].composition_targets:
        assert t.tolerance == 0.05
    for t in points[1].composition_targets:
        assert t.tolerance == 0.03


def test_grid_expand_composition_points_overrides_axes() -> None:
    grid = PolicyGrid(
        name="mixed",
        composition_axes=(
            CompositionGridAxis(
                species=SpeciesClass.LODGEPOLE_PINE,
                values=(0.9,),
                tolerance=0.05,
                provenance=P,
            ),
        ),
        composition_points=(
            {"PL": 0.70, "FD": 0.20},
        ),
        provenance=P,
    )
    points = grid.expand()
    assert len(points) == 1
    assert points[0].name == "pts_PL_0.70_FD_0.20" or "PL_0.70" in points[0].name
    assert len(points[0].composition_targets) == 2


def test_grid_expand_composition_points_no_harvest_axis() -> None:
    grid = PolicyGrid(
        name="comp_only",
        composition_points=(
            {"PL": 0.70, "FD": 0.20},
            {"PL": 0.50, "FD": 0.40},
        ),
        provenance=P,
    )
    points = grid.expand()
    assert len(points) == 2
    for p in points:
        assert p.harvest_policy is None
        assert len(p.composition_targets) == 2


def test_grid_expand_axes_still_works() -> None:
    grid = PolicyGrid(
        name="axes",
        composition_axes=(
            CompositionGridAxis(
                species=SpeciesClass.LODGEPOLE_PINE,
                values=(0.8, 0.9),
                tolerance=0.05,
                provenance=P,
            ),
        ),
        provenance=P,
    )
    points = grid.expand()
    assert len(points) == 2
    shares = {p.composition_targets[0].target_share for p in points}
    assert shares == {0.8, 0.9}
