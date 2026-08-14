"""Fire-in-model tests (P3.4): path walk, salvage action, fire-aware LP solve.

Uses the synthetic bundle fixture (no annex data). Key checks:

- ``path_fire_steps`` compounds the survival factor across null periods,
  resets it after harvest/salvage, and caps salvage at the burned pool.
- A fire-free scenario (zero burn) reproduces the volume-max baseline exactly
  under a uniform zero-discount surface (the P3.6 anchor held at the LP
  level).
- A burning scenario strictly reduces the NPV objective: fire scales every
  green-harvest coefficient down (survival < 1) and the P2.4 salvage margin
  is negative, so no solution can do better than the no-fire optimum.
- Salvage economics govern the decision: at the default negative SPF margin
  the LP salvages nothing; with a positive (subsidised) margin it salvages
  up to the available burned pool.
"""

from __future__ import annotations

import pandas as pd
import pytest

from fresh_fuchs.economy import (
    DiscountRate,
    PriceGroup,
    PriceRecord,
    Product,
    Provenance,
    interior_surface,
)
from fresh_fuchs.instance import (
    BaselineConfig,
    SpeciesClass,
    add_even_flow_problem,
    bootstrap_model,
    prepare_optimization,
    solve_even_flow,
)
from fresh_fuchs.instance.woodstock import write_woodstock_files
from fresh_fuchs.scenario import (
    DisturbanceScenario,
    FireEvent,
    FireLpConfig,
    add_fire_problem,
    add_salvage_action,
    apply_salvage_operability,
    path_fire_steps,
    solve_fire_lp,
)

AU1, AU2 = 1, 2
ZONE_BY_AU = {AU1: "SBPS", AU2: "IDF"}


def _fresh_model(config):
    return prepare_optimization(bootstrap_model(config), max_initial_age=300, config=config)


def _species_map() -> dict:
    return {
        ("29", "managed", "1", "natural", "baseline"): SpeciesClass.LODGEPOLE_PINE,
        ("29", "managed", "1", "planted", "baseline"): SpeciesClass.LODGEPOLE_PINE,
        ("29", "managed", "2", "natural", "baseline"): SpeciesClass.DOUGLAS_FIR,
        ("29", "unmanaged", "2", "natural", "baseline"): SpeciesClass.OTHER,
    }


def _uniform_surface(*, annual_rate: float) -> object:
    """No price differential, given discount rate (mirrors test_npv.py)."""
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


def _scenario(
    *,
    zones: tuple[str, ...] = ("SBPS", "IDF"),
    periods: int = 3,
    annual_burn_rate: float = 0.01,
    severity: str = "Moderate",
) -> DisturbanceScenario:
    events = tuple(
        FireEvent(period=t, zone=zone, annual_burn_rate=annual_burn_rate, severity=severity)
        for zone in zones
        for t in range(1, periods + 1)
    )
    return DisturbanceScenario(
        name="test-scenario",
        seed=1,
        probability=1.0,
        burn_rate_multiplier=1.0,
        price_factor=1.0,
        severity=severity,
        events=events,
    )


def _fire_lp_config() -> FireLpConfig:
    return FireLpConfig(zone_by_au=ZONE_BY_AU)


def test_path_fire_steps_survival_compounds_across_null_periods(synthetic_bundle) -> None:
    config, yields, areas = synthetic_bundle
    write_woodstock_files(areas=areas, yields=yields, config=config)
    model = _fresh_model(config)
    dtk = ("29", "managed", "1", "planted", "baseline")
    scenario = _scenario(annual_burn_rate=0.01)
    p = 1.0 - (1.0 - 0.01) ** 10  # SBPS 0.01/yr over a 10-year period

    dt = model.dtypes[dtk]
    tree = model._bld_tree_m1(
        dt.area(1, 35),
        dtk,
        35,
        {"z": lambda fm, path: 0.0},
        tree=None,
        period=1,
        acodes=["null"],
        compile_c_ycomps=True,
    )
    path = next(iter(tree.paths()))
    steps = path_fire_steps(model, path, scenario=scenario, zone_by_au=ZONE_BY_AU)
    assert [s.acode for s in steps] == ["null", "null", "null"]
    assert steps[0].survival_to == 1.0
    assert steps[1].survival_to == pytest.approx(1.0 - p)
    assert steps[2].survival_to == pytest.approx((1.0 - p) ** 2)
    assert steps[2].salvageable == pytest.approx(
        0.6 * p * steps[2].yield_volume * steps[2].survival_to
    )


def test_path_fire_steps_reset_after_harvest_and_salvage(synthetic_bundle) -> None:
    config, yields, areas = synthetic_bundle
    write_woodstock_files(areas=areas, yields=yields, config=config)
    model = _fresh_model(config)
    model = add_salvage_action(model, max_age=300)
    scenario = _scenario(annual_burn_rate=0.01)
    dtk = ("29", "managed", "1", "natural", "baseline")
    area = model.dtypes[dtk].area(1, 75)

    tree = model._bld_tree_m1(
        area,
        dtk,
        75,
        {"z": lambda fm, path: 0.0},
        tree=None,
        period=1,
        acodes=["harvest", "salvage", "null"],
        compile_c_ycomps=True,
    )
    harvest_path = next(
        path
        for path in tree.paths()
        if tuple(n.data("acode") for n in path) == ("harvest", "null", "null")
    )
    steps = path_fire_steps(model, harvest_path, scenario=scenario, zone_by_au=ZONE_BY_AU)
    assert steps[0].acode == "harvest"
    assert steps[0].green_volume > 0
    assert steps[0].burn_influx == 0.0  # harvest precedes fire: nothing exposed
    assert steps[1].survival_to == 1.0  # regenerated stand: exposure restarts

    salvage_path = next(
        path
        for path in tree.paths()
        if tuple(n.data("acode") for n in path) == ("salvage", "null", "null")
    )
    steps = path_fire_steps(model, salvage_path, scenario=scenario, zone_by_au=ZONE_BY_AU)
    assert steps[0].acode == "salvage"
    assert steps[0].salvaged == pytest.approx(steps[0].salvageable)  # capped at the pool
    assert steps[1].survival_to == 1.0


def test_path_fire_steps_salvage_never_exceeds_burned_pool(synthetic_bundle) -> None:
    config, yields, areas = synthetic_bundle
    write_woodstock_files(areas=areas, yields=yields, config=config)
    model = _fresh_model(config)
    model = add_salvage_action(model, max_age=300)
    scenario = _scenario(annual_burn_rate=0.03, severity="High")
    dtk = ("29", "managed", "1", "natural", "baseline")
    area = model.dtypes[dtk].area(1, 75)
    tree = model._bld_tree_m1(
        area,
        dtk,
        75,
        {"z": lambda fm, path: 0.0},
        tree=None,
        period=1,
        acodes=["harvest", "salvage", "null"],
        compile_c_ycomps=True,
    )
    for path in tree.paths():
        for step in path_fire_steps(model, path, scenario=scenario, zone_by_au=ZONE_BY_AU):
            assert step.salvaged <= step.salvageable + 1e-9
            if step.acode != "harvest":
                assert step.salvageable == pytest.approx(
                    0.85 * step.burn_prob * step.yield_volume * step.survival_to
                )


def test_fire_free_scenario_matches_volume_max_baseline(synthetic_bundle) -> None:
    config, yields, areas = synthetic_bundle
    write_woodstock_files(areas=areas, yields=yields, config=config)

    vol_model = _fresh_model(config)
    vol_problem = add_even_flow_problem(vol_model, BaselineConfig())
    vol_results = solve_even_flow(vol_model, vol_problem)

    fire_model = _fresh_model(config)
    fire_model = add_salvage_action(fire_model, max_age=300)
    fire_cfg = _fire_lp_config()
    scenario = _scenario(annual_burn_rate=0.0)  # fire-free seed
    fire_model = apply_salvage_operability(fire_model, scenario=scenario, zone_by_au=ZONE_BY_AU)
    fire_problem = add_fire_problem(
        fire_model,
        fire_cfg,
        scenario=scenario,
        surface=_uniform_surface(annual_rate=0.0),
        species_by_dtk=_species_map(),
    )
    fire_results = solve_fire_lp(fire_model, fire_problem, scenario=scenario, config=fire_cfg)

    assert fire_problem.status() == "optimal"
    pd.testing.assert_series_equal(
        vol_results["harvest_volume_m3"].round(6),
        fire_results["harvest_volume_m3"].round(6),
    )
    pd.testing.assert_series_equal(
        vol_results["harvest_area_ha"].round(6),
        fire_results["harvest_area_ha"].round(6),
    )
    assert (fire_results["salvage_volume_m3"] == 0).all()


def test_fire_reduces_npv_objective(synthetic_bundle) -> None:
    config, yields, areas = synthetic_bundle
    write_woodstock_files(areas=areas, yields=yields, config=config)

    no_fire = _scenario(annual_burn_rate=0.0)
    burning = _scenario(annual_burn_rate=0.05, severity="Moderate")

    objectives: dict[str, float] = {}
    for label, scenario in (("no_fire", no_fire), ("burning", burning)):
        model = _fresh_model(config)
        model = add_salvage_action(model, max_age=300)
        model = apply_salvage_operability(model, scenario=scenario, zone_by_au=ZONE_BY_AU)
        cfg = _fire_lp_config()
        problem = add_fire_problem(
            model,
            cfg,
            scenario=scenario,
            surface=interior_surface(),
            species_by_dtk=_species_map(),
        )
        problem.solve(verbose=False)
        assert problem.status() == "optimal"
        objectives[label] = float(problem.z())

    # Fire scales every green-harvest coefficient down and adds only
    # non-positive salvage options, so the optimum cannot beat the no-fire
    # optimum.
    assert objectives["no_fire"] > 0
    assert objectives["burning"] < objectives["no_fire"]


def test_salvage_feasible_in_solution_and_economics_govern(synthetic_bundle) -> None:
    config, yields, areas = synthetic_bundle
    write_woodstock_files(areas=areas, yields=yields, config=config)
    scenario = _scenario(annual_burn_rate=0.05, severity="Moderate")

    model = _fresh_model(config)
    model = add_salvage_action(model, max_age=300)
    model = apply_salvage_operability(model, scenario=scenario, zone_by_au=ZONE_BY_AU)
    cfg = _fire_lp_config()
    problem = add_fire_problem(
        model,
        cfg,
        scenario=scenario,
        surface=interior_surface(),  # default P2.4 negative SPF margin
        species_by_dtk=_species_map(),
    )
    results = solve_fire_lp(model, problem, scenario=scenario, config=cfg)

    assert problem.status() == "optimal"
    # Negative salvage margin: a free LP salvages nothing.
    assert (results["salvage_volume_m3"] == 0).all()
    # Salvage-feasibility holds everywhere (salvaged <= salvageable).
    assert (results["salvage_volume_m3"] <= results["salvageable_volume_m3"] + 1e-6).all()


def test_salvage_used_when_margin_positive(synthetic_bundle) -> None:
    config, yields, areas = synthetic_bundle
    write_woodstock_files(areas=areas, yields=yields, config=config)
    scenario = _scenario(annual_burn_rate=0.05, severity="Moderate")

    # A positive salvage margin (prompt-salvage subsidy regime): the LP
    # salvages burned volume up to the available pool instead of leaving it
    # to decay.
    base = interior_surface()
    subsidised = base.model_copy(
        update={
            "salvage": base.salvage.model_copy(
                update={
                    "burned_stumpage_per_m3": 0.0,
                    "burned_transport_per_m3": 0.0,
                    "burned_harvest_premium": 0.0,
                    "burned_price_discount": 1.0,
                }
            )
        }
    )

    model = _fresh_model(config)
    model = add_salvage_action(model, max_age=300)
    model = apply_salvage_operability(model, scenario=scenario, zone_by_au=ZONE_BY_AU)
    cfg = _fire_lp_config()
    problem = add_fire_problem(
        model,
        cfg,
        scenario=scenario,
        surface=subsidised,
        species_by_dtk=_species_map(),
    )
    results = solve_fire_lp(model, problem, scenario=scenario, config=cfg)

    assert problem.status() == "optimal"
    assert float(results["salvage_volume_m3"].sum()) > 0
    assert (results["salvage_volume_m3"] <= results["salvageable_volume_m3"] + 1e-6).all()
    assert (results["salvageable_volume_m3"] > 0).all()


def test_missing_zone_mapping_fails_fast(synthetic_bundle) -> None:
    config, yields, areas = synthetic_bundle
    write_woodstock_files(areas=areas, yields=yields, config=config)
    model = _fresh_model(config)
    scenario = _scenario(annual_burn_rate=0.01)
    dtk = ("29", "managed", "2", "natural", "baseline")
    tree = model._bld_tree_m1(
        model.dtypes[dtk].area(1, 95),
        dtk,
        95,
        {"z": lambda fm, path: 0.0},
        tree=None,
        period=1,
        acodes=["null"],
        compile_c_ycomps=True,
    )
    path = next(iter(tree.paths()))
    with pytest.raises(ValueError):
        path_fire_steps(model, path, scenario=scenario, zone_by_au={AU1: "SBPS"})
