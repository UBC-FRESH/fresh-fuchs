"""Salvage replant integration tests (P6.5): fire dynamics, economics, LP.

Salvage replant actions (``salvage_SX``, ``salvage_PL``, ...) behave like
base ``salvage`` for fire dynamics and salvage economics (burned-price
discount on the salvaged pool) and additionally carry the target species'
replant cost, transitioning the stand to the replant development type.

All tests use the synthetic fixture — no annex bundle required.
"""

from __future__ import annotations

import pytest

from fresh_fuchs.economy import interior_surface
from fresh_fuchs.economy.cashflow import sawlog_basis_salvage_margin
from fresh_fuchs.economy.types import price_group_for_species
from fresh_fuchs.instance import (
    SpeciesClass,
    bootstrap_model,
    prepare_optimization,
)
from fresh_fuchs.instance.replant import (
    add_replant_salvage_actions,
    replant_au_id,
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
from fresh_fuchs.scenario.fire import period_burn_probability, severity_burned_fraction
from fresh_fuchs.scenario.fire_lp import _compile_path_z

AU1, AU2 = 1, 2
ZONE_BY_AU = {AU1: "SBPS", AU2: "IDF"}
DTK1 = ("29", "managed", "1", "natural", "baseline")


def _fresh_model(config):
    return prepare_optimization(bootstrap_model(config), max_initial_age=300, config=config)


def _species_map() -> dict:
    return {
        ("29", "managed", "1", "natural", "baseline"): SpeciesClass.LODGEPOLE_PINE,
        ("29", "managed", "1", "planted", "baseline"): SpeciesClass.LODGEPOLE_PINE,
        ("29", "managed", "2", "natural", "baseline"): SpeciesClass.DOUGLAS_FIR,
        ("29", "unmanaged", "2", "natural", "baseline"): SpeciesClass.OTHER,
    }


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


def _subsidised_surface(*, charge_replant: bool = False):
    """Positive salvage margin (prompt-salvage subsidy regime)."""
    base = interior_surface()
    return base.model_copy(
        update={
            "salvage": base.salvage.model_copy(
                update={
                    "burned_stumpage_per_m3": 0.0,
                    "burned_transport_per_m3": 0.0,
                    "burned_harvest_premium": 0.0,
                    "burned_price_discount": 1.0,
                }
            ),
            "charge_replant_in_npv": charge_replant,
        }
    )


def _salvage_replant_model(config, target_species, scenario):
    """Model with base salvage + salvage replant actions, operability applied."""
    model = _fresh_model(config)
    model = add_salvage_action(model, max_age=300)
    model = add_replant_salvage_actions(model, target_species=target_species)
    model = apply_salvage_operability(model, scenario=scenario, zone_by_au=ZONE_BY_AU)
    return model


# ---------------------------------------------------------------------------
# Registration (standalone: no harvest replant actions required)
# ---------------------------------------------------------------------------


class TestSalvageReplantRegistration:
    def test_replant_dtypes_precreated_without_harvest_replant(
        self, synthetic_bundle
    ) -> None:
        """Salvage replant alone must precreate replant DTKs (tree builder
        follows the salvage_SX transition even if no harvest_SX exists)."""
        config, yields, areas = synthetic_bundle
        write_woodstock_files(areas=areas, yields=yields, config=config)
        model = _fresh_model(config)
        model = add_salvage_action(model, max_age=300)
        model = add_replant_salvage_actions(model, target_species=(SpeciesClass.SPRUCE,))
        replant_dtk = ("29", "managed", replant_au_id("1", SpeciesClass.SPRUCE),
                       "natural", "baseline")
        assert replant_dtk in model.dtypes
        assert replant_dtk[2] == "1-SX"

    def test_transition_targets_replant_au(self, synthetic_bundle) -> None:
        config, yields, areas = synthetic_bundle
        write_woodstock_files(areas=areas, yields=yields, config=config)
        model = _fresh_model(config)
        model = add_salvage_action(model, max_age=300)
        model = add_replant_salvage_actions(model, target_species=(SpeciesClass.SPRUCE,))
        transitions = model.dtypes[DTK1].transitions["salvage_SX", -1]
        (target_mask, prob, _y, age, _tr, _ta, _tc) = transitions[0]
        assert prob == 1.0
        assert age == 0
        assert target_mask[2] == "1-SX"


# ---------------------------------------------------------------------------
# path_fire_steps with salvage replant actions
# ---------------------------------------------------------------------------


class TestSalvageReplantPathFireSteps:
    def _salvage_path(self, model, acodes, dtk=DTK1, age=75):
        area = model.dtypes[dtk].area(1, age)
        tree = model._bld_tree_m1(
            area,
            dtk,
            age,
            {"z": lambda fm, path: 0.0},
            tree=None,
            period=1,
            acodes=acodes,
            compile_c_ycomps=True,
        )
        return next(p for p in tree.paths() if p[0].data("acode") == acodes[0])

    def test_salvage_replant_step_pool_and_reset(self, synthetic_bundle) -> None:
        config, yields, areas = synthetic_bundle
        write_woodstock_files(areas=areas, yields=yields, config=config)
        model = _salvage_replant_model(
            config, (SpeciesClass.SPRUCE,), _scenario(annual_burn_rate=0.05)
        )
        path = self._salvage_path(model, ["salvage_SX", "null"])
        steps = path_fire_steps(
            model, path, scenario=_scenario(annual_burn_rate=0.05), zone_by_au=ZONE_BY_AU
        )
        step0 = steps[0]
        assert step0.acode == "salvage_SX"
        prob = period_burn_probability(0.05, model.period_length)
        expected_pool = severity_burned_fraction("Moderate") * prob * step0.yield_volume
        assert step0.salvaged == pytest.approx(expected_pool)
        assert step0.salvaged > 0
        assert steps[1].survival_to == 1.0  # regenerated stand

    def test_salvage_replant_switches_development_type(self, synthetic_bundle) -> None:
        config, yields, areas = synthetic_bundle
        write_woodstock_files(areas=areas, yields=yields, config=config)
        model = _salvage_replant_model(
            config, (SpeciesClass.SPRUCE,), _scenario(annual_burn_rate=0.05)
        )
        path = self._salvage_path(model, ["salvage_SX", "null"])
        assert path[0].data("dtk")[2] == "1"
        assert path[1].data("dtk")[2] == "1-SX"  # species switch on the path


# ---------------------------------------------------------------------------
# Objective: burned price + target-species replant cost
# ---------------------------------------------------------------------------


class TestSalvageReplantObjective:
    def _path_and_model(self, synthetic_bundle):
        config, yields, areas = synthetic_bundle
        write_woodstock_files(areas=areas, yields=yields, config=config)
        scenario = _scenario(annual_burn_rate=0.05)
        model = _salvage_replant_model(config, (SpeciesClass.SPRUCE,), scenario)
        area = model.dtypes[DTK1].area(1, 75)
        tree = model._bld_tree_m1(
            area,
            DTK1,
            75,
            {"z": lambda fm, path: 0.0},
            tree=None,
            period=1,
            acodes=["salvage_SX", "salvage", "null"],
            compile_c_ycomps=True,
        )
        return model, scenario, tree

    def test_burned_margin_applied(self, synthetic_bundle) -> None:
        model, scenario, tree = self._path_and_model(synthetic_bundle)
        surface = _subsidised_surface(charge_replant=False)
        path = next(p for p in tree.paths() if p[0].data("acode") == "salvage_SX")
        z = _compile_path_z(
            model,
            path,
            scenario=scenario,
            config=FireLpConfig(zone_by_au=ZONE_BY_AU),
            surface=surface,
            species_by_dtk=_species_map(),
        )
        steps = path_fire_steps(model, path, scenario=scenario, zone_by_au=ZONE_BY_AU)
        margin = sawlog_basis_salvage_margin(
            surface, price_group_for_species(SpeciesClass.LODGEPOLE_PINE)
        )
        expected = sum(
            surface.discount_factor(s.period, period_length=model.period_length)
            * s.salvaged
            * margin
            for s in steps
        )
        assert margin > 0  # subsidised regime
        assert z == pytest.approx(expected)

    def test_replant_cost_charged_for_target_species(self, synthetic_bundle) -> None:
        model, scenario, tree = self._path_and_model(synthetic_bundle)
        path = next(p for p in tree.paths() if p[0].data("acode") == "salvage_SX")
        cfg = FireLpConfig(zone_by_au=ZONE_BY_AU)
        z_off = _compile_path_z(
            model, path, scenario=scenario, config=cfg,
            surface=_subsidised_surface(charge_replant=False),
            species_by_dtk=_species_map(),
        )
        z_on = _compile_path_z(
            model, path, scenario=scenario, config=cfg,
            surface=_subsidised_surface(charge_replant=True),
            species_by_dtk=_species_map(),
        )
        # Single salvage_SX event at period 1: cost enters once, discounted.
        surface = interior_surface()
        discount = surface.discount_factor(1, period_length=model.period_length)
        expected_diff = discount * surface.replant_cost_per_ha(SpeciesClass.SPRUCE)
        assert z_off - z_on == pytest.approx(expected_diff)

    def test_base_salvage_has_no_replant_cost(self, synthetic_bundle) -> None:
        model, scenario, tree = self._path_and_model(synthetic_bundle)
        path = next(p for p in tree.paths() if p[0].data("acode") == "salvage")
        cfg = FireLpConfig(zone_by_au=ZONE_BY_AU)
        z_off = _compile_path_z(
            model, path, scenario=scenario, config=cfg,
            surface=_subsidised_surface(charge_replant=False),
            species_by_dtk=_species_map(),
        )
        z_on = _compile_path_z(
            model, path, scenario=scenario, config=cfg,
            surface=_subsidised_surface(charge_replant=True),
            species_by_dtk=_species_map(),
        )
        assert z_on == pytest.approx(z_off)


# ---------------------------------------------------------------------------
# Operability pruning covers salvage replant actions
# ---------------------------------------------------------------------------


class TestSalvageReplantOperability:
    def test_fire_free_periods_pruned(self, synthetic_bundle) -> None:
        config, yields, areas = synthetic_bundle
        write_woodstock_files(areas=areas, yields=yields, config=config)
        scenario = _scenario(annual_burn_rate=0.0)  # no fire anywhere
        model = _salvage_replant_model(config, (SpeciesClass.SPRUCE,), scenario)
        for dtk in (DTK1, ("29", "managed", "1-SX", "natural", "baseline")):
            dt = model.dtypes[dtk]
            for period in model.periods:
                assert dt.operability["salvage"][period] == (0, -1)
                assert dt.operability["salvage_SX"][period] == (0, -1)

    def test_burning_periods_operable(self, synthetic_bundle) -> None:
        config, yields, areas = synthetic_bundle
        write_woodstock_files(areas=areas, yields=yields, config=config)
        scenario = _scenario(annual_burn_rate=0.05)
        model = _salvage_replant_model(config, (SpeciesClass.SPRUCE,), scenario)
        dt = model.dtypes[DTK1]
        for period in model.periods:
            lo, hi = dt.operability["salvage_SX"][period]
            assert lo <= hi  # window open somewhere in burn periods

    def test_no_salvage_replant_codes_leaves_model_unchanged(
        self, synthetic_bundle
    ) -> None:
        config, yields, areas = synthetic_bundle
        write_woodstock_files(areas=areas, yields=yields, config=config)
        model = _fresh_model(config)
        model = add_salvage_action(model, max_age=300)
        model = apply_salvage_operability(
            model, scenario=_scenario(annual_burn_rate=0.0), zone_by_au=ZONE_BY_AU
        )
        assert "salvage_SX" not in model.dtypes[DTK1].operability


# ---------------------------------------------------------------------------
# LP solve with salvage replant actions
# ---------------------------------------------------------------------------


class TestSalvageReplantLpSolve:
    def test_salvage_replant_solves_and_replants(self, synthetic_bundle) -> None:
        """With only ``salvage_SX`` available (no base salvage in the LP) and
        a subsidised margin, the LP salvages and every salvaged ha is
        replanted to spruce."""
        config, yields, areas = synthetic_bundle
        write_woodstock_files(areas=areas, yields=yields, config=config)
        scenario = _scenario(annual_burn_rate=0.05)
        model = _salvage_replant_model(config, (SpeciesClass.SPRUCE,), scenario)
        cfg = FireLpConfig(
            zone_by_au=ZONE_BY_AU,
            action_codes=("null", "harvest", "salvage_SX"),
        )
        problem = add_fire_problem(
            model,
            cfg,
            scenario=scenario,
            surface=_subsidised_surface(),
            species_by_dtk=_species_map(),
        )
        results = solve_fire_lp(model, problem, scenario=scenario, config=cfg)

        assert problem.status() == "optimal"
        assert float(results["salvage_volume_m3"].sum()) > 0
        # Salvage-feasibility holds everywhere (salvaged <= salvageable).
        assert (
            results["salvage_volume_m3"] <= results["salvageable_volume_m3"] + 1e-6
        ).all()
        # All salvaged area is replanted to spruce.
        sx_replant = sum(
            d.get("SX", 0.0) for d in results["replant_area_by_species"]
        )
        assert sx_replant == pytest.approx(float(results["salvage_area_ha"].sum()))
        assert sx_replant > 0

    def test_replant_cost_reduces_objective(self, synthetic_bundle) -> None:
        config, yields, areas = synthetic_bundle
        write_woodstock_files(areas=areas, yields=yields, config=config)
        scenario = _scenario(annual_burn_rate=0.05)

        objectives = {}
        for charge in (False, True):
            model = _salvage_replant_model(config, (SpeciesClass.SPRUCE,), scenario)
            cfg = FireLpConfig(
                zone_by_au=ZONE_BY_AU,
                action_codes=("null", "harvest", "salvage_SX"),
            )
            problem = add_fire_problem(
                model,
                cfg,
                scenario=scenario,
                surface=_subsidised_surface(charge_replant=charge),
                species_by_dtk=_species_map(),
            )
            problem.solve(verbose=False)
            assert problem.status() == "optimal"
            objectives[charge] = float(problem.z())

        assert objectives[True] < objectives[False]

    def test_backward_compatible_default_action_codes(self, synthetic_bundle) -> None:
        """Default LP (no salvage replant codes) is unchanged."""
        config, yields, areas = synthetic_bundle
        write_woodstock_files(areas=areas, yields=yields, config=config)
        scenario = _scenario(annual_burn_rate=0.05)
        model = _fresh_model(config)
        model = add_salvage_action(model, max_age=300)
        model = apply_salvage_operability(model, scenario=scenario, zone_by_au=ZONE_BY_AU)
        cfg = FireLpConfig(zone_by_au=ZONE_BY_AU)
        problem = add_fire_problem(
            model,
            cfg,
            scenario=scenario,
            surface=interior_surface(),  # default negative SPF margin
            species_by_dtk=_species_map(),
        )
        results = solve_fire_lp(model, problem, scenario=scenario, config=cfg)
        assert problem.status() == "optimal"
        assert (results["salvage_volume_m3"] == 0).all()
        assert all(
            not d for d in results["replant_area_by_species"]
        )
