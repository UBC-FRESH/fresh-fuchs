"""Outer policy layer tests (P4.1): records and policy rows in the inner LP."""

from __future__ import annotations

import pytest

from fresh_fuchs.economy import interior_surface
from fresh_fuchs.economy.npv import DevelopmentTypeKey
from fresh_fuchs.economy.types import Provenance
from fresh_fuchs.instance import (
    BaselineConfig,
    InstanceConfig,
    SpeciesClass,
    add_even_flow_problem,
    bootstrap_model,
    prepare_optimization,
    solve_even_flow,
)
from fresh_fuchs.instance.woodstock import write_woodstock_files
from fresh_fuchs.outer import (
    CompositionTarget,
    HarvestPolicy,
    HarvestPolicyMode,
    PolicyRecord,
    apply_rotation_constraints,
)

P = Provenance(source="test", as_of="T0", units="multiplier", basis="p4 test")

ZONE_BY_AU = {1: "SBPS", 2: "IDF"}


def _species_map() -> dict[DevelopmentTypeKey, SpeciesClass]:
    return {
        ("29", "managed", "1", "natural", "baseline"): SpeciesClass.LODGEPOLE_PINE,
        ("29", "managed", "1", "planted", "baseline"): SpeciesClass.LODGEPOLE_PINE,
        ("29", "managed", "2", "natural", "baseline"): SpeciesClass.DOUGLAS_FIR,
        ("29", "unmanaged", "2", "natural", "baseline"): SpeciesClass.OTHER,
    }


def _context(tmp_path) -> InstanceConfig:
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


def _policy(**overrides) -> PolicyRecord:
    defaults = dict(
        name="p",
        provenance=P,
        harvest_policy=HarvestPolicy(
            mode=HarvestPolicyMode.AAC_PROXY,
            aac_level_m3_per_yr=40_000.0,
            provenance=P,
        ),
    )
    defaults.update(overrides)
    return PolicyRecord(**defaults)


def _solve_baseline(config, policy, species_map):
    model = prepare_optimization(bootstrap_model(config), max_initial_age=300, config=config)
    if (
        policy is not None
        and policy.harvest_policy is not None
        and policy.harvest_policy.mode is HarvestPolicyMode.ROTATION_CONSTRAINTS
    ):
        model = apply_rotation_constraints(model, policy=policy, species_by_dtk=species_map)
    problem = add_even_flow_problem(
        model, BaselineConfig(), policy=policy, species_by_dtk=species_map
    )
    return model, solve_even_flow(model, problem), problem


def test_policy_flows_through_fire_pipeline(tmp_path) -> None:
    """Composition targets fold into the fire-aware inner LP via run_scenario_lp."""
    from fresh_fuchs.scenario.fire import DEFAULT_SEVERITY
    from fresh_fuchs.scenario.pipeline import run_scenario_lp
    from fresh_fuchs.scenario.records import DisturbanceScenario, FireEvent

    config = _context(tmp_path)
    species_map = _species_map()
    policy = PolicyRecord(
        name="comp_pl_90_fire",
        provenance=P,
        composition_targets=(
            CompositionTarget(
                species=SpeciesClass.LODGEPOLE_PINE,
                target_share=0.9,
                tolerance=0.05,
                provenance=P,
            ),
        ),
    )
    scenario = DisturbanceScenario(
        name="burn",
        seed=0,
        probability=1.0,
        burn_rate_multiplier=1.0,
        events=tuple(FireEvent(period=t, zone="SBPS", annual_burn_rate=0.01) for t in (1, 2, 3)),
        severity=DEFAULT_SEVERITY,
    )
    record = run_scenario_lp(
        config=config,
        scenario=scenario,
        surface=interior_surface(),
        species_by_dtk=species_map,
        zone_by_au=ZONE_BY_AU,
        max_initial_age=300,
        policy=policy,
    )
    assert record.status == "optimal"
    assert all(p.harvest_volume_m3 >= 0 for p in record.periods)


def _harvested_mix_by_species(model, problem, species_map) -> dict[SpeciesClass, float]:
    schedule = model.compile_schedule(problem)
    total: dict[SpeciesClass, float] = {}
    for dtk, _age, area, acode, _period, _etype in schedule:
        if acode != "harvest":
            continue
        sp = species_map.get(tuple(dtk), SpeciesClass.OTHER)
        total[sp] = total.get(sp, 0.0) + area
    return total


def test_composition_target_binds_species_mix(tmp_path) -> None:
    """A 90% PL composition target forces the harvested-area mix to PL."""
    config = _context(tmp_path)
    species_map = _species_map()
    policy = PolicyRecord(
        name="comp_pl_90",
        provenance=P,
        composition_targets=(
            CompositionTarget(
                species=SpeciesClass.LODGEPOLE_PINE,
                target_share=0.9,
                tolerance=0.05,
                provenance=P,
            ),
        ),
    )
    model, _results, problem = _solve_baseline(config, policy, species_map)

    mix = _harvested_mix_by_species(model, problem, species_map)
    share = mix[SpeciesClass.LODGEPOLE_PINE] / sum(mix.values())
    assert 0.85 <= share <= 0.95


def test_aac_proxy_pins_harvest_volume(tmp_path) -> None:
    """aac_proxy pins per-period harvest volume to the policy level."""
    config = _context(tmp_path)
    _m, plain, _p = _solve_baseline(config, None, _species_map())
    mean_period = plain["harvest_volume_m3"].mean()
    policy = _policy(
        name="aac",
        harvest_policy=HarvestPolicy(
            mode=HarvestPolicyMode.AAC_PROXY,
            aac_level_m3_per_yr=0.9 * mean_period / config.period_length,
            aac_tolerance=0.05,
            provenance=P,
        ),
    )
    _model, results, _problem = _solve_baseline(config, policy, _species_map())
    hi = 0.9 * mean_period * 1.05
    assert results["harvest_volume_m3"].max() == pytest.approx(hi, rel=1e-6)
    assert all(abs(v - hi) <= 1e-6 * hi for v in results["harvest_volume_m3"])


def test_rotation_floor_binds_pl_harvest_age(tmp_path) -> None:
    """rotation floor prevents below-floor PL harvest steps."""
    config = _context(tmp_path)
    species_map = _species_map()
    floor = 140

    _m, _r, no_policy = _solve_baseline(config, None, species_map)
    young_pl = [
        step[1]
        for step in _m.compile_schedule(no_policy)
        if step[3] == "harvest"
        and species_map.get(tuple(step[0]), SpeciesClass.OTHER) is SpeciesClass.LODGEPOLE_PINE
    ]
    assert any(age < floor for age in young_pl), "baseline should harvest young PL"

    policy = _policy(
        name="rot_pl_140",
        harvest_policy=HarvestPolicy(
            mode=HarvestPolicyMode.ROTATION_CONSTRAINTS,
            rotation_floor={SpeciesClass.LODGEPOLE_PINE: floor},
            provenance=P,
        ),
    )
    model = prepare_optimization(bootstrap_model(config), max_initial_age=300, config=config)
    model = apply_rotation_constraints(model, policy=policy, species_by_dtk=species_map)
    problem = add_even_flow_problem(
        model, BaselineConfig(), policy=policy, species_by_dtk=species_map
    )
    problem.solve(verbose=False)
    schedule = model.compile_schedule(problem)
    pl_ages = [
        step[1]
        for step in schedule
        if step[3] == "harvest"
        and species_map.get(tuple(step[0]), SpeciesClass.OTHER) is SpeciesClass.LODGEPOLE_PINE
    ]
    assert all(age >= floor for age in pl_ages)


def test_policy_validation_rejects_bad_targets() -> None:
    with pytest.raises(ValueError):
        CompositionTarget(
            species=SpeciesClass.SPRUCE, target_share=1.5, tolerance=0.1, provenance=P
        )
    with pytest.raises(ValueError):
        HarvestPolicy(
            mode=HarvestPolicyMode.AAC_PROXY,
            aac_level_m3_per_yr=0.0,
            provenance=P,
        )
    with pytest.raises(ValueError):
        HarvestPolicy(
            mode=HarvestPolicyMode.ROTATION_CONSTRAINTS,
            rotation_floor={SpeciesClass.SPRUCE: 100},
            rotation_ceiling={SpeciesClass.SPRUCE: 80},
            provenance=P,
        )


def test_aac_row_matches_reported_volume_without_policy(tmp_path) -> None:
    """Baseline without a policy is unchanged: general rows absent."""
    config = _context(tmp_path)
    _model, plain, _problem = _solve_baseline(config, None, _species_map())
    assert list(plain.columns) == [
        "period",
        "harvest_area_ha",
        "harvest_volume_m3",
        "growing_stock_m3",
    ]
