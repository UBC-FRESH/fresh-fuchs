"""Scenario-record and generator tests (P3.3): seeds, events, round-trips."""

from __future__ import annotations

import json

import pytest

from fresh_fuchs.economy.types import Provenance
from fresh_fuchs.scenario.distributions import (
    DistributionFamily,
    ParameterDistribution,
    UncertaintyDimension,
    UncertaintyVector,
)
from fresh_fuchs.scenario.fire import (
    DEFAULT_SEVERITY,
)
from fresh_fuchs.scenario.records import (
    DisturbanceScenario,
    FireEvent,
    ScenarioGenerationParams,
    build_scenario,
    generate_scenarios,
    write_scenario_catalogue,
)

P = Provenance(source="test", as_of="T0", units="multiplier", basis="test catalogue")

ZONE_RATES = {"IDF": 0.005, "SBPS": 0.01}


def _params(**overrides) -> ScenarioGenerationParams:
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
    defaults = dict(
        n_scenarios=3,
        master_seed=42,
        horizon=2,
        period_length=10,
        zone_burn_rates=ZONE_RATES,
        vector=vector,
        severity=DEFAULT_SEVERITY,
        provenance=P,
    )
    defaults.update(overrides)
    return ScenarioGenerationParams(**defaults)


def test_fire_event_validates_severity() -> None:
    FireEvent(period=1, zone="SBPS", annual_burn_rate=0.01, severity="High")
    with pytest.raises(ValueError):
        FireEvent(period=1, zone="SBPS", annual_burn_rate=0.01, severity="Napalm")


def test_build_scenario_expands_events() -> None:
    scenario = build_scenario(index=0, params=_params())
    assert scenario.seed == 42
    assert scenario.probability == pytest.approx(1 / 3)
    # 2 zones x 2 periods = 4 events, deterministic order (IDF before SBPS).
    assert len(scenario.events) == 4
    assert [e.zone for e in scenario.events] == ["IDF", "IDF", "SBPS", "SBPS"]
    assert [e.period for e in scenario.events] == [1, 2, 1, 2]
    multiplier = scenario.burn_rate_multiplier
    assert scenario.events[0].annual_burn_rate == pytest.approx(0.005 * multiplier)
    assert scenario.events[2].annual_burn_rate == pytest.approx(0.01 * multiplier)
    assert scenario.price_factor == pytest.approx(1.0)


def test_generate_scenarios_is_bit_stable() -> None:
    first = generate_scenarios(_params())
    second = generate_scenarios(_params())
    assert [s.to_dict() for s in first] == [s.to_dict() for s in second]
    assert len(first) == 3
    assert [s.name for s in first] == ["scenario_0000", "scenario_0001", "scenario_0002"]
    assert [s.seed for s in first] == [42, 43, 44]


def test_generate_scenarios_differs_across_seeds() -> None:
    a = [s.burn_rate_multiplier for s in generate_scenarios(_params())]
    b = [s.burn_rate_multiplier for s in generate_scenarios(_params(master_seed=99))]
    assert a != b


def test_scenario_to_dict_round_trip() -> None:
    scenario = build_scenario(index=1, params=_params())
    payload = scenario.to_dict()
    assert set(payload) == {"name", "probability", "parameters"}
    params = payload["parameters"]
    assert params["seed"] == 43
    assert params["severity"] == DEFAULT_SEVERITY
    assert len(params["events"]) == 4
    restored = DisturbanceScenario.from_dict(payload)
    assert restored == scenario


def test_write_scenario_catalogue(tmp_path) -> None:
    params = _params(n_scenarios=2)
    scenarios = generate_scenarios(params)
    path = write_scenario_catalogue(scenarios, params, tmp_path / "catalogue.json")
    data = json.loads(path.read_text())
    assert len(data["catalogue"]) == 2
    assert data["provenance"]["master_seed"] == 42
    assert data["provenance"]["n_scenarios"] == 2
    assert data["catalogue"][0]["parameters"]["seed"] == 42


def test_generation_params_validates() -> None:
    with pytest.raises(ValueError):
        _params(n_scenarios=0)
    with pytest.raises(ValueError):
        _params(horizon=0)


def test_fixed_multiplier_applied_verbatim() -> None:
    vector = UncertaintyVector(
        distributions={
            UncertaintyDimension.FIRE_BURN_RATE: ParameterDistribution(
                name="burn_rate_multiplier",
                family=DistributionFamily.FIXED,
                provenance=P,
                value=2.0,
            ),
            UncertaintyDimension.PRICE: ParameterDistribution(
                name="price_factor",
                family=DistributionFamily.FIXED,
                provenance=P,
                value=0.9,
            ),
        }
    )
    params = _params(vector=vector)
    scenario = build_scenario(index=0, params=params)
    assert scenario.burn_rate_multiplier == pytest.approx(2.0)
    assert scenario.price_factor == pytest.approx(0.9)
    assert scenario.events[0].annual_burn_rate == pytest.approx(0.01)
