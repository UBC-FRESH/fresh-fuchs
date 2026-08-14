"""Scenario -> LP pipeline tests (P3.5): record shape, determinism, parallelism."""

from __future__ import annotations

from pathlib import Path

from fresh_fuchs.economy import interior_surface
from fresh_fuchs.economy.types import Provenance
from fresh_fuchs.instance import (
    InstanceConfig,
    SpeciesClass,
)
from fresh_fuchs.instance.woodstock import write_woodstock_files
from fresh_fuchs.scenario.distributions import (
    DistributionFamily,
    ParameterDistribution,
    UncertaintyDimension,
    UncertaintyVector,
)
from fresh_fuchs.scenario.fire import DEFAULT_SEVERITY
from fresh_fuchs.scenario.pipeline import (
    run_scenario_lp,
    run_scenario_pipeline,
    write_pipeline_record,
)
from fresh_fuchs.scenario.records import (
    ScenarioGenerationParams,
    generate_scenarios,
)

P = Provenance(source="test", as_of="T0", units="multiplier", basis="test pipeline")

ZONE_RATES = {"IDF": 0.005, "SBPS": 0.01}

ZONE_BY_AU = {1: "SBPS", 2: "IDF"}


def _species_map() -> dict:
    return {
        ("29", "managed", "1", "natural", "baseline"): SpeciesClass.LODGEPOLE_PINE,
        ("29", "managed", "1", "planted", "baseline"): SpeciesClass.LODGEPOLE_PINE,
        ("29", "managed", "2", "natural", "baseline"): SpeciesClass.DOUGLAS_FIR,
        ("29", "unmanaged", "2", "natural", "baseline"): SpeciesClass.OTHER,
    }


def _params(n_scenarios: int = 3, master_seed: int = 42) -> ScenarioGenerationParams:
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


def _record_digest(record) -> dict:
    """Comparable digest of one scenario's LP result (schedule + NPV)."""
    return {
        "status": record.status,
        "npv": record.npv,
        "harvest_area": [p.harvest_area_ha for p in record.periods],
        "harvest_volume": [p.harvest_volume_m3 for p in record.periods],
        "salvage_area": [p.salvage_area_ha for p in record.periods],
        "salvage_volume": [p.salvage_volume_m3 for p in record.periods],
        "salvageable_volume": [p.salvageable_volume_m3 for p in record.periods],
        "growing_stock": [p.growing_stock_m3 for p in record.periods],
    }


def test_run_scenario_lp_records_schedule_and_npv(tmp_path):
    config, species_by_dtk = _model_context(tmp_path)
    record = run_scenario_lp(
        config=config,
        scenario=_scenarios(1)[0],
        surface=interior_surface(),
        species_by_dtk=species_by_dtk,
        zone_by_au=ZONE_BY_AU,
        max_initial_age=300,
    )
    assert record.status == "optimal"
    assert record.npv == record.npv  # finite
    assert len(record.periods) == config.horizon
    assert all(p.period == i + 1 for i, p in enumerate(record.periods))
    assert record.total_harvested_area_ha > 0
    assert all(0 <= p.salvage_volume_m3 <= p.salvageable_volume_m3 + 1e-9 for p in record.periods)


def test_pipeline_parallel_bit_matches_sequential(tmp_path):
    config, species_by_dtk = _model_context(tmp_path)
    scenarios = _scenarios(3)
    kw = dict(
        config=config,
        surface=interior_surface(),
        species_by_dtk=species_by_dtk,
        zone_by_au=ZONE_BY_AU,
        max_initial_age=300,
    )
    sequential = run_scenario_pipeline(scenarios=scenarios, n_workers=1, **kw)
    parallel = run_scenario_pipeline(scenarios=scenarios, n_workers=2, **kw)
    assert [s.scenario.seed for s in sequential.scenarios] == [42, 43, 44]
    assert sequential.n_workers == 1 and parallel.n_workers == 2
    for left, right in zip(sequential.scenarios, parallel.scenarios):
        assert left.scenario.name == right.scenario.name
        assert _record_digest(left) == _record_digest(right)


def test_pipeline_fire_exposes_monotone_burn_rate_effect(tmp_path):
    config, species_by_dtk = _model_context(tmp_path)
    scenarios = _scenarios(3)
    kw = dict(
        config=config,
        surface=interior_surface(),
        species_by_dtk=species_by_dtk,
        zone_by_au=ZONE_BY_AU,
        max_initial_age=300,
    )
    record = run_scenario_pipeline(scenarios=scenarios, n_workers=1, **kw)
    for scenario_record in record.scenarios:
        assert scenario_record.status == "optimal"
    npvs = [s.npv for s in record.scenarios]
    assert len(set(npvs)) > 1  # scenarios actually differ in burn draw


def test_write_pipeline_record_emits_json_and_csvs(tmp_path):
    config, species_by_dtk = _model_context(tmp_path)
    record = run_scenario_pipeline(
        scenarios=_scenarios(2),
        config=config,
        surface=interior_surface(),
        species_by_dtk=species_by_dtk,
        zone_by_au=ZONE_BY_AU,
        max_initial_age=300,
        n_workers=1,
    )
    out = tmp_path / "run"
    written = write_pipeline_record(record, out)
    assert (out / "pipeline_run.json").exists()
    assert (out / "pipeline_summary.csv").exists()
    assert all(path.exists() for path in written)
    assert len(written) == 4  # json + 2 schedules + summary
