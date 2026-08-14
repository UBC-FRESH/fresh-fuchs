"""Phase 3 acceptance tests (P3.6): baseline reproduction, monotonicity,
bit-stability.

Synthetic-bundle checks (public-safe). The real-bundle reproduction of the
NPV-max baseline is a recorded run (validation report; needs private data).
"""

from __future__ import annotations

from pathlib import Path

from fresh_fuchs.economy import (
    DiscountRate,
    PriceGroup,
    PriceRecord,
    Product,
    interior_surface,
)
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
)
from fresh_fuchs.scenario.records import (
    DisturbanceScenario,
    FireEvent,
    ScenarioGenerationParams,
    generate_scenarios,
)

P = Provenance(source="test", as_of="T0", units="multiplier", basis="test acceptance")

ZONE_RATES = {"IDF": 0.005, "SBPS": 0.01}

ZONE_BY_AU = {1: "SBPS", 2: "IDF"}


def _species_map() -> dict:
    return {
        ("29", "managed", "1", "natural", "baseline"): SpeciesClass.LODGEPOLE_PINE,
        ("29", "managed", "1", "planted", "baseline"): SpeciesClass.LODGEPOLE_PINE,
        ("29", "managed", "2", "natural", "baseline"): SpeciesClass.DOUGLAS_FIR,
        ("29", "unmanaged", "2", "natural", "baseline"): SpeciesClass.OTHER,
    }


def _context(tmp_path: Path) -> InstanceConfig:
    from tests.conftest import build_synthetic_areas, build_synthetic_yields

    config = InstanceConfig(
        model_name="synthetic",
        model_path=tmp_path,
        horizon=3,
        period_length=10,
        max_age=300,
        min_harvest_age=60,
    )
    write_woodstock_files(
        areas=build_synthetic_areas(), yields=build_synthetic_yields(), config=config
    )
    return config


def _scenario_at(multiplier: float, name: str = "scenario") -> DisturbanceScenario:
    """A deterministic scenario burning both zones every period at a multiplier."""
    return DisturbanceScenario(
        name=name,
        seed=0,
        probability=1.0,
        burn_rate_multiplier=multiplier,
        events=tuple(
            FireEvent(period=p, zone=z, annual_burn_rate=rate * multiplier)
            for p in (1, 2, 3)
            for z, rate in (("SBPS", 0.01), ("IDF", 0.005))
        ),
        severity=DEFAULT_SEVERITY,
    )


def _uniform_surface(*, annual_rate: float) -> object:
    """No price differential, given discount rate (mirrors test_fire_lp.py)."""
    base = interior_surface()
    provenance = Provenance(
        source="test", as_of="T0", units="CAD/m3", basis="no price differential"
    )
    prices = [
        PriceRecord(
            product=Product.SAWLOG,
            price_group=PriceGroup.SPF,
            price_per_m3=127.0,
            provenance=provenance,
        ),
        PriceRecord(
            product=Product.SAWLOG,
            price_group=PriceGroup.DFLARCH,
            price_per_m3=127.0,
            provenance=provenance,
        ),
    ]
    return base.model_copy(
        update={
            "prices": prices,
            "discount": DiscountRate(annual_rate=annual_rate, provenance=provenance),
        }
    )


def test_pipeline_fire_free_reproduces_volume_max_baseline(tmp_path) -> None:
    """Fire-free through the full scenario pipeline == the volume-max baseline.

    Under a uniform zero-discount surface the fire-aware NPV objective
    reduces to volume, so a p=0 scenario solved by ``run_scenario_lp`` must
    reproduce the deterministic even-flow baseline exactly.
    """
    import pandas as pd

    from fresh_fuchs.instance import (
        BaselineConfig,
        add_even_flow_problem,
        bootstrap_model,
        prepare_optimization,
    )
    from fresh_fuchs.instance.baseline import solve_even_flow

    config = _context(tmp_path)
    vol_model = prepare_optimization(bootstrap_model(config), max_initial_age=300, config=config)
    vol_problem = add_even_flow_problem(vol_model, BaselineConfig())
    vol_results = solve_even_flow(vol_model, vol_problem)

    firefree = _scenario_at(0.0, name="fire_free")
    record = run_scenario_lp(
        config=config,
        scenario=firefree,
        surface=_uniform_surface(annual_rate=0.0),
        species_by_dtk=_species_map(),
        zone_by_au=ZONE_BY_AU,
        max_initial_age=300,
    )
    assert record.status == "optimal"
    harvest = [p.harvest_volume_m3 for p in record.periods]
    pd.testing.assert_series_equal(
        vol_results["harvest_volume_m3"].round(6),
        pd.Series(harvest, name="harvest_volume_m3").round(6),
    )
    assert all(p.salvage_volume_m3 == 0 for p in record.periods)


def test_burn_rate_monotone_decreases_npv(tmp_path) -> None:
    """Higher burn multiplier -> strictly lower total NPV (same seeds)."""
    config = _context(tmp_path)
    npvs: list[float] = []
    for multiplier in (0.0, 0.5, 1.0, 2.0):
        record = run_scenario_lp(
            config=config,
            scenario=_scenario_at(multiplier),
            surface=interior_surface(),
            species_by_dtk=_species_map(),
            zone_by_au=ZONE_BY_AU,
            max_initial_age=300,
        )
        assert record.status == "optimal"
        npvs.append(record.npv)
    assert all(b < a for a, b in zip(npvs, npvs[1:]))


def test_pipeline_seed_fixed_runs_bit_stable(tmp_path) -> None:
    """Two pipeline runs under the same master seed produce identical records."""
    config = _context(tmp_path)
    vector = UncertaintyVector(
        distributions={
            UncertaintyDimension.FIRE_BURN_RATE: ParameterDistribution(
                name="burn_rate_multiplier",
                family=DistributionFamily.FIXED,
                provenance=P,
                value=1.0,
            ),
            UncertaintyDimension.PRICE: ParameterDistribution(
                name="price_factor",
                family=DistributionFamily.FIXED,
                provenance=P,
                value=1.0,
            ),
        }
    )
    params = ScenarioGenerationParams(
        n_scenarios=3,
        master_seed=7,
        horizon=3,
        period_length=10,
        zone_burn_rates=ZONE_RATES,
        vector=vector,
        severity=DEFAULT_SEVERITY,
        provenance=P,
    )
    scenarios = generate_scenarios(params)
    kw = dict(
        config=config,
        surface=interior_surface(),
        species_by_dtk=_species_map(),
        zone_by_au=ZONE_BY_AU,
        max_initial_age=300,
    )
    first = run_scenario_pipeline(scenarios=scenarios, n_workers=1, **kw)
    second = run_scenario_pipeline(scenarios=scenarios, n_workers=1, **kw)
    for left, right in zip(first.scenarios, second.scenarios):
        assert left.model_dump() == right.model_dump()
