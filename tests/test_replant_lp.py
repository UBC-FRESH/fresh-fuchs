"""Replant LP wiring tests (Phase 3): objective, even-flow, fire dynamics.

All tests use the synthetic fixture — no annex bundle required.
"""

from __future__ import annotations

import pandas as pd

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
from fresh_fuchs.instance.replant import (
    add_replant_actions,
    target_species_from_acode,
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
    annual_burn_rate: float = 0.0,
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


def _fire_lp_config(*, action_codes: tuple[str, ...] | None = None) -> FireLpConfig:
    kwargs: dict = {"zone_by_au": ZONE_BY_AU}
    if action_codes is not None:
        kwargs["action_codes"] = action_codes
    return FireLpConfig(**kwargs)


# ---------------------------------------------------------------------------
# target_species_from_acode
# ---------------------------------------------------------------------------


class TestTargetSpeciesFromAcode:
    def test_harvest_sx(self) -> None:
        assert target_species_from_acode("harvest_SX") is SpeciesClass.SPRUCE

    def test_harvest_pl(self) -> None:
        assert target_species_from_acode("harvest_PL") is SpeciesClass.LODGEPOLE_PINE

    def test_harvest_fd(self) -> None:
        assert target_species_from_acode("harvest_FD") is SpeciesClass.DOUGLAS_FIR

    def test_salvage_sx(self) -> None:
        assert target_species_from_acode("salvage_SX") is SpeciesClass.SPRUCE

    def test_base_harvest_returns_none(self) -> None:
        assert target_species_from_acode("harvest") is None

    def test_base_salvage_returns_none(self) -> None:
        assert target_species_from_acode("salvage") is None

    def test_null_returns_none(self) -> None:
        assert target_species_from_acode("null") is None

    def test_unknown_returns_none(self) -> None:
        assert target_species_from_acode("unknown_XX") is None


# ---------------------------------------------------------------------------
# path_fire_steps with replant actions
# ---------------------------------------------------------------------------


class TestReplantPathFireSteps:
    def test_replant_action_resets_survival(self, synthetic_bundle) -> None:
        config, yields, areas = synthetic_bundle
        write_woodstock_files(areas=areas, yields=yields, config=config)
        model = _fresh_model(config)
        model = add_replant_actions(model, target_species=(SpeciesClass.SPRUCE,))
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
            acodes=["harvest_SX", "null"],
            compile_c_ycomps=True,
        )
        harvest_path = next(
            path
            for path in tree.paths()
            if path[0].data("acode") == "harvest_SX"
        )
        steps = path_fire_steps(model, harvest_path, scenario=scenario, zone_by_au=ZONE_BY_AU)
        assert steps[0].acode == "harvest_SX"
        assert steps[0].green_volume > 0
        assert steps[0].burn_influx == 0.0
        assert steps[1].survival_to == 1.0  # regenerated stand

    def test_replant_action_in_even_flow(self, synthetic_bundle) -> None:
        config, yields, areas = synthetic_bundle
        write_woodstock_files(areas=areas, yields=yields, config=config)
        model = _fresh_model(config)
        model = add_replant_actions(model, target_species=(SpeciesClass.SPRUCE,))

        scenario = _scenario(annual_burn_rate=0.0)
        dtk = ("29", "managed", "1", "natural", "baseline")
        area = model.dtypes[dtk].area(1, 75)

        tree = model._bld_tree_m1(
            area,
            dtk,
            75,
            {"z": lambda fm, path: 0.0},
            tree=None,
            period=1,
            acodes=["harvest_SX", "null"],
            compile_c_ycomps=True,
        )
        for path in tree.paths():
            steps = path_fire_steps(model, path, scenario=scenario, zone_by_au=ZONE_BY_AU)
            for step in steps:
                if step.acode.startswith("harvest"):
                    assert step.green_volume > 0


# ---------------------------------------------------------------------------
# LP solve with replant actions
# ---------------------------------------------------------------------------


class TestReplantLpSolve:
    def test_lp_solves_with_replant_actions(self, synthetic_bundle) -> None:
        config, yields, areas = synthetic_bundle
        write_woodstock_files(areas=areas, yields=yields, config=config)

        model = _fresh_model(config)
        model = add_replant_actions(
            model, target_species=(SpeciesClass.SPRUCE, SpeciesClass.DOUGLAS_FIR)
        )
        model = add_salvage_action(model, max_age=300)

        scenario = _scenario(annual_burn_rate=0.0)
        model = apply_salvage_operability(model, scenario=scenario, zone_by_au=ZONE_BY_AU)

        action_codes = ("null", "harvest", "salvage", "harvest_SX", "harvest_FD")
        cfg = _fire_lp_config(action_codes=action_codes)
        problem = add_fire_problem(
            model,
            cfg,
            scenario=scenario,
            surface=interior_surface(),
            species_by_dtk=_species_map(),
        )
        problem.solve(verbose=False)
        assert problem.status() == "optimal"

    def test_replant_actions_in_objective(self, synthetic_bundle) -> None:
        config, yields, areas = synthetic_bundle
        write_woodstock_files(areas=areas, yields=yields, config=config)

        model = _fresh_model(config)
        model = add_replant_actions(model, target_species=(SpeciesClass.SPRUCE,))
        model = add_salvage_action(model, max_age=300)

        scenario = _scenario(annual_burn_rate=0.0)
        model = apply_salvage_operability(model, scenario=scenario, zone_by_au=ZONE_BY_AU)

        action_codes = ("null", "harvest", "salvage", "harvest_SX")
        cfg = _fire_lp_config(action_codes=action_codes)
        problem = add_fire_problem(
            model,
            cfg,
            scenario=scenario,
            surface=interior_surface(),
            species_by_dtk=_species_map(),
        )
        problem.solve(verbose=False)
        assert problem.status() == "optimal"
        assert float(problem.z()) > 0

    def test_replant_cost_reduces_objective(self, synthetic_bundle) -> None:
        config, yields, areas = synthetic_bundle
        write_woodstock_files(areas=areas, yields=yields, config=config)

        scenario = _scenario(annual_burn_rate=0.0)

        # Without replant actions (no replant cost)
        model_no = _fresh_model(config)
        model_no = add_salvage_action(model_no, max_age=300)
        model_no = apply_salvage_operability(model_no, scenario=scenario, zone_by_au=ZONE_BY_AU)
        cfg_no = _fire_lp_config(action_codes=("null", "harvest", "salvage"))
        problem_no = add_fire_problem(
            model_no,
            cfg_no,
            scenario=scenario,
            surface=interior_surface(),
            species_by_dtk=_species_map(),
        )
        problem_no.solve(verbose=False)

        # With replant actions and replant cost charged
        model_with = _fresh_model(config)
        model_with = add_replant_actions(
            model_with, target_species=(SpeciesClass.SPRUCE,)
        )
        model_with = add_salvage_action(model_with, max_age=300)
        model_with = apply_salvage_operability(model_with, scenario=scenario, zone_by_au=ZONE_BY_AU)

        surface_with_cost = interior_surface()
        surface_with_cost.charge_replant_in_npv = True

        cfg_with = _fire_lp_config(
            action_codes=("null", "harvest", "salvage", "harvest_SX")
        )
        problem_with = add_fire_problem(
            model_with,
            cfg_with,
            scenario=scenario,
            surface=surface_with_cost,
            species_by_dtk=_species_map(),
        )
        problem_with.solve(verbose=False)

        assert problem_no.status() == "optimal"
        assert problem_with.status() == "optimal"
        # Replant cost reduces the objective
        assert float(problem_with.z()) < float(problem_no.z())

    def test_even_flow_aggregates_replant_actions(self, synthetic_bundle) -> None:
        config, yields, areas = synthetic_bundle
        write_woodstock_files(areas=areas, yields=yields, config=config)

        model = _fresh_model(config)
        model = add_replant_actions(
            model, target_species=(SpeciesClass.SPRUCE, SpeciesClass.DOUGLAS_FIR)
        )
        model = add_salvage_action(model, max_age=300)

        scenario = _scenario(annual_burn_rate=0.0)
        model = apply_salvage_operability(model, scenario=scenario, zone_by_au=ZONE_BY_AU)

        action_codes = ("null", "harvest", "salvage", "harvest_SX", "harvest_FD")
        cfg = _fire_lp_config(action_codes=action_codes)
        problem = add_fire_problem(
            model,
            cfg,
            scenario=scenario,
            surface=interior_surface(),
            species_by_dtk=_species_map(),
        )
        results = solve_fire_lp(
            model,
            problem,
            scenario=scenario,
            config=cfg,
            replant_action_codes=("harvest_SX", "harvest_FD"),
        )

        assert problem.status() == "optimal"
        # Total harvest area across replant actions matches the report
        assert results["harvest_area_ha"].sum() > 0
        assert results["harvest_volume_m3"].sum() > 0

    def test_backward_compatible_without_replant(self, synthetic_bundle) -> None:
        config, yields, areas = synthetic_bundle
        write_woodstock_files(areas=areas, yields=yields, config=config)

        vol_model = _fresh_model(config)
        vol_problem = add_even_flow_problem(vol_model, BaselineConfig())
        vol_results = solve_even_flow(vol_model, vol_problem)

        fire_model = _fresh_model(config)
        fire_model = add_salvage_action(fire_model, max_age=300)
        fire_cfg = _fire_lp_config()
        scenario = _scenario(annual_burn_rate=0.0)
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
