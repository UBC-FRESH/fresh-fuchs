"""Replant composition constraint tests (Phase 4).

Tests for composition constraints binding on replant action area
(target species), three-phase transition schedule, and backward
compatibility with source-species composition.
"""

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
from fresh_fuchs.instance.replant import add_replant_actions, target_species_from_acode
from fresh_fuchs.instance.woodstock import write_woodstock_files
from fresh_fuchs.outer import (
    CompositionGridAxis,
    CompositionTarget,
    PolicyGrid,
    PolicyRecord,
)
from fresh_fuchs.outer.policy import (
    _resolve_species,
    _share_by_period,
)
from fresh_fuchs.scenario import (
    DisturbanceScenario,
    FireEvent,
    FireLpConfig,
    add_fire_problem,
    add_salvage_action,
    apply_salvage_operability,
    solve_fire_lp,
)
from fresh_fuchs.scenario.fire import DEFAULT_SEVERITY

P = Provenance(source="test", as_of="T0", units="multiplier", basis="p4 test")

ZONE_BY_AU = {1: "SBPS", 2: "IDF"}

REPLANT_ACTIONS = ("harvest_SX", "harvest_FD")

SPECIES_MAP: dict[DevelopmentTypeKey, SpeciesClass] = {
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


def _fresh_model(config):
    return prepare_optimization(
        bootstrap_model(config), max_initial_age=300, config=config
    )


def _scenario(annual_burn_rate: float = 0.01):
    return DisturbanceScenario(
        name="burn",
        seed=0,
        probability=1.0,
        burn_rate_multiplier=1.0,
        events=tuple(
            FireEvent(period=t, zone="SBPS", annual_burn_rate=annual_burn_rate)
            for t in (1, 2, 3)
        ),
        severity=DEFAULT_SEVERITY,
    )


# --- share_by_period unit tests ---


def test_share_by_period_free_only():
    target = CompositionTarget(
        species=SpeciesClass.SPRUCE,
        target_share=0.4,
        tolerance=0.05,
        n_free_periods=3,
        provenance=P,
    )
    result = _share_by_period(target, periods=[1, 2, 3])
    assert result == {1: 1.0, 2: 1.0, 3: 1.0}


def test_share_by_period_binding_only():
    target = CompositionTarget(
        species=SpeciesClass.SPRUCE,
        target_share=0.4,
        tolerance=0.05,
        n_free_periods=0,
        n_ramp_periods=0,
        provenance=P,
    )
    result = _share_by_period(target, periods=[1, 2, 3])
    assert result == {1: 0.05, 2: 0.05, 3: 0.05}


def test_share_by_period_ramp():
    target = CompositionTarget(
        species=SpeciesClass.SPRUCE,
        target_share=0.4,
        tolerance=0.05,
        n_free_periods=1,
        n_ramp_periods=3,
        provenance=P,
    )
    result = _share_by_period(target, periods=[1, 2, 3, 4, 5])
    # Period 1: free -> 1.0
    # Period 2: ramp step 1/3 -> 1.0 - (1/3)*0.95
    # Period 3: ramp step 2/3 -> 1.0 - (2/3)*0.95
    # Period 4: ramp step 3/3 -> 1.0 - (3/3)*0.95 = 0.05
    # Period 5: binding -> 0.05
    assert result[1] == pytest.approx(1.0)
    assert result[2] == pytest.approx(1.0 - (1 / 3) * 0.95)
    assert result[3] == pytest.approx(1.0 - (2 / 3) * 0.95)
    assert result[4] == pytest.approx(0.05)
    assert result[5] == pytest.approx(0.05)


def test_share_by_period_defaults_no_free_no_ramp():
    target = CompositionTarget(
        species=SpeciesClass.SPRUCE,
        target_share=0.5,
        tolerance=0.1,
        provenance=P,
    )
    result = _share_by_period(target, periods=[1, 2, 3])
    assert result == {1: 0.1, 2: 0.1, 3: 0.1}


# --- resolve_species tests ---


def test_resolve_species_with_replant_actions():
    sp = _resolve_species(
        "harvest_SX",
        ("29", "managed", "1", "natural", "baseline"),
        SPECIES_MAP,
        replant_actions=REPLANT_ACTIONS,
    )
    assert sp is SpeciesClass.SPRUCE


def test_resolve_species_with_replant_actions_base_harvest():
    sp = _resolve_species(
        "harvest",
        ("29", "managed", "1", "natural", "baseline"),
        SPECIES_MAP,
        replant_actions=REPLANT_ACTIONS,
    )
    # Base "harvest" falls back to source species
    assert sp is SpeciesClass.LODGEPOLE_PINE


def test_resolve_species_without_replant_actions():
    sp = _resolve_species(
        "harvest",
        ("29", "managed", "1", "natural", "baseline"),
        SPECIES_MAP,
        replant_actions=None,
    )
    assert sp is SpeciesClass.LODGEPOLE_PINE


# --- CompositionTarget validation ---


def test_composition_target_three_phase_fields():
    target = CompositionTarget(
        species=SpeciesClass.SPRUCE,
        target_share=0.4,
        tolerance=0.05,
        n_free_periods=2,
        n_ramp_periods=3,
        provenance=P,
    )
    assert target.n_free_periods == 2
    assert target.n_ramp_periods == 3


def test_composition_target_defaults():
    target = CompositionTarget(
        species=SpeciesClass.SPRUCE,
        target_share=0.5,
        tolerance=0.1,
        provenance=P,
    )
    assert target.n_free_periods == 0
    assert target.n_ramp_periods == 0


# --- Replant composition LP integration ---


def _solve_with_replant_composition(config, policy):
    model = prepare_optimization(
        bootstrap_model(config), max_initial_age=300, config=config
    )
    model = add_replant_actions(
        model, target_species=(SpeciesClass.SPRUCE, SpeciesClass.DOUGLAS_FIR)
    )
    model = add_salvage_action(model, max_age=300)

    scenario = _scenario(annual_burn_rate=0.01)
    model = apply_salvage_operability(model, scenario=scenario, zone_by_au=ZONE_BY_AU)

    cfg = FireLpConfig(
        zone_by_au=ZONE_BY_AU,
        action_codes=("null", "harvest", "salvage", "harvest_SX", "harvest_FD"),
    )
    problem = add_fire_problem(
        model,
        cfg,
        scenario=scenario,
        surface=interior_surface(),
        species_by_dtk=SPECIES_MAP,
        policy=policy,
    )
    results = solve_fire_lp(
        model,
        problem,
        scenario=scenario,
        config=cfg,
        replant_action_codes=("harvest_SX", "harvest_FD"),
    )
    return model, results, problem


def _replanted_mix_by_species(model, problem) -> dict[SpeciesClass, float]:
    schedule = model.compile_schedule(problem)
    total: dict[SpeciesClass, float] = {}
    for dtk, _age, area, acode, _period, _etype in schedule:
        if not acode.startswith("harvest"):
            continue
        sp = target_species_from_acode(acode)
        if sp is None:
            sp = SPECIES_MAP.get(tuple(dtk), SpeciesClass.OTHER)
        total[sp] = total.get(sp, 0.0) + area
    return total


def test_replant_composition_binds_spruce_share(tmp_path):
    """Composition constraint on harvest_SX rebalances replanted area toward spruce."""
    config = _context(tmp_path)
    policy = PolicyRecord(
        name="replant_comp_sx",
        provenance=P,
        composition_targets=(
            CompositionTarget(
                species=SpeciesClass.SPRUCE,
                target_share=0.6,
                tolerance=0.05,
                provenance=P,
            ),
        ),
        replant_actions=REPLANT_ACTIONS,
    )
    model, results, problem = _solve_with_replant_composition(config, policy)
    assert problem.status() == "optimal"
    mix = _replanted_mix_by_species(model, problem)
    total_area = sum(mix.values())
    if total_area > 0:
        sx_share = mix.get(SpeciesClass.SPRUCE, 0.0) / total_area
        assert 0.55 <= sx_share <= 0.65, f"spruce share {sx_share:.3f} outside [0.55, 0.65]"


def test_three_phase_free_periods_unconstrained(tmp_path):
    """Free periods produce an unconstrained LP (same as no composition)."""
    config = _context(tmp_path)
    # Policy with free periods = horizon: constraint never binds
    policy_free = PolicyRecord(
        name="replant_free",
        provenance=P,
        composition_targets=(
            CompositionTarget(
                species=SpeciesClass.SPRUCE,
                target_share=0.99,
                tolerance=0.01,
                n_free_periods=3,
                provenance=P,
            ),
        ),
        replant_actions=REPLANT_ACTIONS,
    )
    _, results_free, problem_free = _solve_with_replant_composition(config, policy_free)
    # Policy with same target but no free periods: constraint binds hard
    policy_bind = PolicyRecord(
        name="replant_bind",
        provenance=P,
        composition_targets=(
            CompositionTarget(
                species=SpeciesClass.SPRUCE,
                target_share=0.99,
                tolerance=0.01,
                n_free_periods=0,
                provenance=P,
            ),
        ),
        replant_actions=REPLANT_ACTIONS,
    )
    _, results_bind, problem_bind = _solve_with_replant_composition(config, policy_bind)
    assert problem_free.status() == "optimal"
    assert problem_bind.status() == "optimal"
    # Free version should have >= harvest area (less constrained)
    free_ha = results_free["harvest_area_ha"].sum()
    bind_ha = results_bind["harvest_area_ha"].sum()
    assert free_ha >= bind_ha - 1e-6


def test_backward_compat_source_species_composition(tmp_path):
    """Without replant_actions, composition binds on source species (existing behavior)."""
    config = _context(tmp_path)
    model = prepare_optimization(
        bootstrap_model(config), max_initial_age=300, config=config
    )
    # No replant actions — pure baseline
    policy = PolicyRecord(
        name="source_comp",
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
    problem = add_even_flow_problem(
        model, BaselineConfig(), policy=policy, species_by_dtk=SPECIES_MAP
    )
    solve_even_flow(model, problem)
    assert problem.status() == "optimal"
    # Check harvested-area share matches constraint
    schedule = model.compile_schedule(problem)
    total_area = 0.0
    pl_area = 0.0
    for dtk, _age, area, acode, _period, _etype in schedule:
        if acode != "harvest":
            continue
        total_area += area
        sp = SPECIES_MAP.get(tuple(dtk), SpeciesClass.OTHER)
        if sp is SpeciesClass.LODGEPOLE_PINE:
            pl_area += area
    if total_area > 0:
        share = pl_area / total_area
        assert 0.85 <= share <= 0.95, f"PL share {share:.3f} outside [0.85, 0.95]"


# --- Grid expansion tests ---


def test_grid_axis_passes_three_phase():
    axis = CompositionGridAxis(
        species=SpeciesClass.SPRUCE,
        values=(0.3, 0.5),
        tolerance=0.05,
        n_free_periods=1,
        n_ramp_periods=2,
        provenance=P,
    )
    assert axis.n_free_periods == 1
    assert axis.n_ramp_periods == 2


def test_grid_expansion_with_three_phase():
    grid = PolicyGrid(
        name="test3p",
        composition_axes=[
            CompositionGridAxis(
                species=SpeciesClass.LODGEPOLE_PINE,
                values=(0.7, 0.9),
                tolerance=0.05,
                n_free_periods=1,
                n_ramp_periods=1,
                provenance=P,
            ),
        ],
        harvest_axis=None,
        provenance=P,
    )
    cells = grid.expand()
    assert len(cells) == 2
    for policy in cells:
        assert len(policy.composition_targets) == 1
        ct = policy.composition_targets[0]
        assert ct.n_free_periods == 1
        assert ct.n_ramp_periods == 1


def test_composition_point_three_phase():
    grid = PolicyGrid(
        name="testcp",
        composition_points=(
            {
                "SX": 0.4,
                "PL": 0.6,
                "tolerance": 0.05,
                "n_free_periods": 2,
                "n_ramp_periods": 1,
            },
        ),
        harvest_axis=None,
        provenance=P,
    )
    cells = grid.expand()
    assert len(cells) == 1
    policy = cells[0]
    assert len(policy.composition_targets) == 2
    for ct in policy.composition_targets:
        assert ct.n_free_periods == 2
        assert ct.n_ramp_periods == 1


def test_grid_backward_compat_no_three_phase():
    """Grid without n_free/n_ramp fields produces default (0, 0) on targets."""
    grid = PolicyGrid(
        name="testbc",
        composition_axes=[
            CompositionGridAxis(
                species=SpeciesClass.LODGEPOLE_PINE,
                values=(0.7,),
                tolerance=0.05,
                provenance=P,
            ),
        ],
        harvest_axis=None,
        provenance=P,
    )
    cells = grid.expand()
    policy = cells[0]
    ct = policy.composition_targets[0]
    assert ct.n_free_periods == 0
    assert ct.n_ramp_periods == 0
